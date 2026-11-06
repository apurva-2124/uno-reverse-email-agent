import importlib.util
import json
import multiprocessing
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / '.agents/skills/uno-reverse/scripts/ledger.py'
spec = importlib.util.spec_from_file_location('ledger', SCRIPT)
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)


def example():
    return {'mailbox':'owner@example.com','profile':{'business':'Acme','description':'We organize feedback.',
            'cta':'https://example.com/demo','signature':'Alex','source':'manual','source_version':'1'}}


def competing_run(path, name, queue):
    state = ledger.Ledger(path)
    try:
        try:
            state.begin(name)
            queue.put('started')
        except ValueError:
            queue.put('blocked')
    finally:
        state.close()


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.time = 1793910000.0
        self.state = ledger.Ledger(self.temp.name,create=True,clock=lambda:self.time)
        self.preview = self.state.configure(example())

    def tearDown(self):
        self.state.close()
        self.temp.cleanup()

    def activate(self):
        self.state.activate(self.state.preview()['hash'],'User explicitly enabled the displayed policy')
        self.state.begin('run-1')

    def candidate(self, brand='vendor'):
        return {'brand':brand,'company':'Vendor','recipient':'sam@vendor.example','source_id':brand+'-source',
                'thread_id':brand+'-thread','source_message_ids':[brand+'-source'],'source_received_at':self.time,
                'subject':'Re: Demo?','evidence':'Signature names Vendor; body offers a demo.'}

    def test_default_is_local_without_invitation(self):
        c = self.preview['config']
        self.assertEqual(c['brandvault_choice'],'local')
        self.assertFalse(c['invitation']['enabled'])
        self.assertNotIn('Optimly',self.preview['example'])
        self.assertIsNone(self.state.status()['policy'])

    def test_brandvault_connection_does_not_enable_invitation(self):
        c = example()
        c.update(brandvault_choice='existing')
        c['profile'].update(source='brandvault',source_version='published-3')
        p = self.state.configure(c)
        self.assertNotIn('Optimly',p['example'])
        self.assertFalse(p['config']['invitation']['enabled'])

    def test_invitation_is_explicit_exact_and_removable(self):
        c = example()
        line = 'P.S. You can create a free BrandVault with Optimly: https://optimly.ai/'
        c['invitation'] = {'enabled':True,'text':line}
        p = self.state.configure(c)
        self.assertIn(line,p['example'])
        self.assertEqual(p['example'].count(line),1)
        self.state.activate(p['hash'],'User approved invitation and activated policy')
        c['invitation'] = {'enabled':False,'text':''}
        p = self.state.configure(c)
        self.assertNotIn(line,p['example'])
        self.assertIsNone(self.state.status()['policy'])

    def test_stale_policy_cannot_be_activated(self):
        c = example(); c['profile']['description']='A new fact.'
        self.state.configure(c)
        with self.assertRaisesRegex(ValueError,'changed'):
            self.state.activate(self.preview['hash'],'Old consent')

    def test_blank_consent_and_unconfigured_send_rejected(self):
        with self.assertRaises(ValueError): self.state.activate(self.preview['hash'],'')
        with self.assertRaisesRegex(ValueError,'No active'): self.state.begin('run')

    def test_exact_rendered_plan_and_policy_receipt(self):
        self.activate()
        r = self.state.reserve('run-1',self.candidate())
        self.assertEqual(r['plan']['body'],ledger.render(self.preview['config'],'Vendor'))
        self.assertEqual(r['receipt_hash'],ledger.digest(r['plan']))
        self.assertEqual(r['plan']['mailbox'],'owner@example.com')
        self.state.result(r['attempt'],'accepted','gmail-1')
        self.state.end('run-1',self.time)
        self.assertEqual(self.state.status()['attempts'][0]['provider_id'],'gmail-1')

    def test_crash_unknown_requires_reconciliation_and_explicit_resume(self):
        self.activate()
        r = self.state.reserve('run-1',self.candidate())
        other = ledger.Ledger(self.temp.name,clock=lambda:self.time)
        try:
            with self.assertRaises(ValueError): other.begin('second')
            other.end('run-1')
            self.assertTrue(other.status()['paused'])
            with self.assertRaises(ValueError): other.resume('Please resume')
            other.result(r['attempt'],'accepted','gmail-found')
            self.assertTrue(other.status()['paused'])
            other.resume('User reconciled and resumed')
            other.begin('second')
        finally: other.close()

    def test_unknown_never_releases_brand_or_source(self):
        self.activate()
        r = self.state.reserve('run-1',self.candidate())
        self.state.result(r['attempt'],'unknown')
        self.state.end('run-1')
        with self.assertRaises(ValueError): self.state.resume('resume')
        self.assertEqual(len(self.state.status()['attempts']),1)
        with self.assertRaises(ValueError): self.state.result(r['attempt'],'failed')

    def test_accepted_outcome_is_immutable(self):
        self.activate(); r=self.state.reserve('run-1',self.candidate())
        self.state.result(r['attempt'],'accepted','gmail-1')
        self.state.result(r['attempt'],'accepted','gmail-1')
        with self.assertRaises(ValueError): self.state.result(r['attempt'],'accepted','gmail-2')
        with self.assertRaises(ValueError): self.state.result(r['attempt'],'unknown')

    def test_brand_dedup_across_runs_and_config_changes(self):
        self.activate(); r=self.state.reserve('run-1',self.candidate())
        self.state.result(r['attempt'],'accepted','gmail-1'); self.state.end('run-1')
        self.state.configure(example()); self.time+=6
        self.state.activate(self.state.preview()['hash'],'User reactivated')
        self.state.begin('run-2')
        c=self.candidate();c['source_id']='new';c['source_message_ids']=['new']
        with self.assertRaisesRegex(ValueError,'already reserved'): self.state.reserve('run-2',c)

    def test_caps_and_spacing(self):
        c=example();c['daily_cap']=1
        self.state.configure(c);self.activate()
        r=self.state.reserve('run-1',self.candidate())
        self.state.result(r['attempt'],'accepted','gmail-1')
        self.time+=6
        with self.assertRaisesRegex(ValueError,'cap'): self.state.reserve('run-1',self.candidate('other'))
        self.state.end('run-1');self.time+=86400;self.state.begin('tomorrow')
        self.state.reserve('tomorrow',self.candidate('other'))
        with self.assertRaises(ValueError): self.state.reserve('tomorrow',self.candidate('third'))

    def test_five_second_spacing_independent_of_daily_cap(self):
        self.activate(); self.state.reserve('run-1',self.candidate())
        with self.assertRaisesRegex(ValueError,'five seconds'): self.state.reserve('run-1',self.candidate('other'))

    def test_scope_and_suppression(self):
        self.activate()
        c=self.candidate();c['source_received_at']-=1
        with self.assertRaisesRegex(ValueError,'scope'): self.state.reserve('run-1',c)
        self.state.suppress('vendor','Opt-out')
        with self.assertRaisesRegex(ValueError,'Suppressed'): self.state.reserve('run-1',self.candidate())

    def test_mixed_case_address_suppression(self):
        self.activate()
        self.state.suppress('Sam@Vendor.Example', 'Opt-out')
        with self.assertRaisesRegex(ValueError, 'Suppressed'):
            self.state.reserve('run-1', self.candidate())

    def test_new_config_cannot_switch_mailbox_or_modify_open_run(self):
        c=example();c['mailbox']='other@example.com'
        with self.assertRaisesRegex(ValueError,'Mailbox'): self.state.configure(c)
        self.activate()
        with self.assertRaisesRegex(ValueError,'active run'): self.state.configure(example())

    def test_two_processes_cannot_begin_concurrent_runs(self):
        self.state.activate(self.preview['hash'],'User activated')
        ctx=multiprocessing.get_context('spawn');queue=ctx.Queue()
        processes=[ctx.Process(target=competing_run,args=(self.temp.name,str(i),queue)) for i in range(2)]
        for p in processes:p.start()
        for p in processes:p.join(10);self.assertEqual(p.exitcode,0)
        self.assertEqual(sorted(queue.get(timeout=2) for _ in processes),['blocked','started'])

    def test_pause_survives_reactivation(self):
        self.state.pause('User paused')
        self.state.activate(self.preview['hash'],'Activate policy')
        with self.assertRaisesRegex(ValueError,'paused'):self.state.begin('run')
        self.state.resume('User explicitly resumed');self.state.begin('run')

    def test_event_dedup_and_cursor(self):
        self.activate()
        self.assertTrue(self.state.event('reply-1',{'category':'interested'})['new'])
        self.assertFalse(self.state.event('reply-1',{'category':'interested'})['new'])
        self.state.end('run-1',self.time)
        self.assertEqual(self.state.status()['last_scan'],self.time)

    def test_missing_ledger_is_not_initialized_during_status(self):
        path=Path(self.temp.name)/'missing'
        result=subprocess.run([sys.executable,str(SCRIPT),'--state',str(path),'status'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertFalse(path.exists())

    def test_rejects_recipient_injection_and_dynamic_urls(self):
        self.activate()
        for recipient in ['a@example.com, b@example.com','a@example.com\r\nBcc: victim@example.com','noreply@example.com']:
            c=self.candidate();c['recipient']=recipient
            with self.subTest(recipient=recipient),self.assertRaises(ValueError):self.state.reserve('run-1',c)
        with self.assertRaises(ValueError):ledger.render(self.preview['config'],'Acme https://evil.example')

    def test_no_secret_fields_or_hidden_invitation(self):
        c=example();c['api_key']='secret'
        with self.assertRaises(ValueError):self.state.configure(c)
        c=example();c['invitation']={'enabled':False,'text':'Hidden promotion'}
        with self.assertRaises(ValueError):self.state.configure(c)
        c=example();c['invitation']={'enabled':True,'text':'Try it: https://evil.example'}
        with self.assertRaises(ValueError):self.state.configure(c)

    def test_cli_configuration_and_preview(self):
        path=Path(self.temp.name)/'config.json';path.write_text(json.dumps(example()))
        result=subprocess.run([sys.executable,str(SCRIPT),'--state',self.temp.name,'configure','--input',str(path)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(json.loads(result.stdout)['config']['invitation']['enabled'])
        self.assertEqual((Path(self.temp.name)/'ledger.sqlite3').stat().st_mode & 0o777,0o600)
