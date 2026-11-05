from dataclasses import replace
from email import policy
from email.parser import BytesParser
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest
from uno_reverse import classifier
from uno_reverse.composer import mime, reply_subject, threading
from uno_reverse.mailbox import FakeMailbox, create_demo
from uno_reverse.models import Message, Profile, address, digest
from uno_reverse.replies import check_replies, classify_reply
from uno_reverse.storage import Store
from uno_reverse.workflow import Workflow


def competing_send(directory, candidate_id, timestamp, queue):
    store = Store(directory)
    try:
        workflow = Workflow(store, FakeMailbox(Path(directory) / 'mailbox.json'), clock=lambda: timestamp)
        try:
            queue.put(workflow.send(candidate_id))
        except ValueError as exc:
            queue.put(str(exc))
    finally:
        store.close()


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.mailbox = create_demo(self.root / 'mailbox.json')
        self.time = 2_000_000_000.0
        self.flow = Workflow(self.store, self.mailbox, clock=lambda: self.time)
        self.profile = Profile('Example', 'example.test', 'We organize work.', 'https://example.test', 'Alex')
        self.flow.set_profile(self.profile)
        self.flow.set_brands({'acme.example': {'id': 'acme', 'name': 'Acme'}})
        self.run = self.flow.scan(since=0)
        self.candidate = next(c for c in self.store.candidates() if c['state'] == 'ready')['id']

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def approve(self, candidate=None):
        cid = candidate or self.candidate
        self.flow.approve(cid, digest(self.store.candidate(cid)['plan']))

    def add_sales(self, brand='other', timestamp=None):
        brands = self.store.get('brands')
        brands[f'{brand}.example'] = {'id': brand, 'name': brand.title()}
        self.store.set('brands', brands)
        message = Message(f'sales-{brand}', f'thread-{brand}', f'seller@{brand}.example', 'A demo?',
                          f'Would you like to book a demo? — {brand.title()}', timestamp or self.time, f'<{brand}@{brand}.example>')
        self.mailbox.append(message)
        return message

    def test_preview_does_not_mutate_mailbox_or_persist_source_bodies(self):
        self.assertEqual(len(self.mailbox.messages()), 3)
        states = {c['source_id']: c['state'] for c in self.store.candidates()}
        self.assertEqual(states, {'sales-1': 'ready', 'security-1': 'excluded', 'personal-1': 'needs_review'})
        self.assertNotIn('Your security verification code is 123456', json.dumps(self.store.export()))
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 0)

    def test_unapproved_send_rejected(self):
        with self.assertRaisesRegex(ValueError, 'not authorized'):
            self.flow.send(self.candidate)
        self.assertEqual(len(self.mailbox.messages()), 3)

    def test_approve_send_idempotent_and_mime_threaded(self):
        self.approve()
        self.assertEqual(self.flow.send(self.candidate), 'accepted_by_gmail')
        self.assertEqual(self.flow.send(self.candidate), 'accepted_by_gmail')
        self.assertEqual(len(self.mailbox.messages()), 4)
        attempt = self.store.db.execute('SELECT * FROM attempts').fetchone()
        msg = BytesParser(policy=policy.default).parsebytes(attempt['mime'])
        self.assertEqual(str(msg['To']), 'sam@acme.example')
        self.assertEqual(str(msg['In-Reply-To']), '<sales-1@acme.example>')
        self.assertIsNone(msg['Cc'])
        self.assertIsNone(msg['Bcc'])
        self.assertEqual(msg.get_content_type(), 'multipart/alternative')
        self.assertEqual(str(msg['Message-ID']), attempt['message_id'])
        self.assertIn('uno reverse', self.mailbox.messages()[0].labels)

    def test_stale_hash_and_edit_invalidate_approval(self):
        old_hash = digest(self.store.candidate(self.candidate)['plan'])
        self.approve()
        self.flow.edit(self.candidate, body='A revised pitch')
        with self.assertRaisesRegex(ValueError, 'not authorized'):
            self.flow.send(self.candidate)
        with self.assertRaisesRegex(ValueError, 'Draft changed'):
            self.flow.approve(self.candidate, old_hash)
        self.approve()
        self.assertEqual(self.flow.send(self.candidate), 'accepted_by_gmail')

    def test_profile_change_needs_redraft_then_approval(self):
        self.approve()
        self.flow.set_profile(replace(self.profile, description='A new approved fact.'))
        with self.assertRaisesRegex(ValueError, 'Profile changed'):
            self.approve()
        self.flow.redraft(self.candidate)
        self.assertIn('A new approved fact.', self.store.candidate(self.candidate)['plan']['body'])
        self.approve()
        self.assertEqual(self.flow.send(self.candidate), 'accepted_by_gmail')

    def test_suppression_and_pause_persist_across_restart(self):
        self.approve()
        self.flow.pause()
        other = Store(self.root)
        try:
            f = Workflow(other, self.mailbox, clock=lambda: self.time)
            with self.assertRaisesRegex(ValueError, 'paused'):
                f.send(self.candidate)
            f.resume()
            f.suppress('acme')
            with self.assertRaisesRegex(ValueError, 'suppressed'):
                f.send(self.candidate)
        finally:
            other.close()

    def test_acceptance_timeout_reconciles_without_resending(self):
        self.approve()
        self.mailbox.send_fault = 'accepted_timeout'
        self.assertEqual(self.flow.send(self.candidate), 'send_unknown')
        self.assertTrue(self.store.get('paused'))
        self.assertEqual(len(self.mailbox.messages()), 4)
        with self.assertRaisesRegex(ValueError, 'Reconcile'):
            self.flow.resume()
        self.assertEqual(self.flow.reconcile(), [self.candidate])
        self.assertTrue(self.store.get('paused'))
        self.flow.resume()
        self.assertEqual(self.flow.send(self.candidate), 'accepted_by_gmail')
        self.assertEqual(len(self.mailbox.messages()), 4)

    def test_unknown_not_found_stays_reserved_and_paused(self):
        self.approve()
        self.mailbox.send_fault = 'unknown'
        self.assertEqual(self.flow.send(self.candidate), 'send_unknown')
        self.assertEqual(self.flow.reconcile(), [])
        self.assertEqual(self.flow.send(self.candidate), 'send_unknown')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM reservations').fetchone()[0], 1)
        self.assertEqual(len(self.mailbox.messages()), 3)

    def test_pre_submission_failure_retry_is_explicit_and_bounded_by_spacing(self):
        self.approve()
        self.mailbox.send_fault = 'before'
        self.assertEqual(self.flow.send(self.candidate), 'failed_before_send')
        self.assertFalse(self.store.get('paused'))
        self.mailbox.send_fault = None
        with self.assertRaisesRegex(ValueError, 'five seconds'):
            self.flow.send(self.candidate)
        self.time += 5
        self.assertEqual(self.flow.send(self.candidate), 'accepted_by_gmail')
        self.assertEqual(len(self.mailbox.messages()), 4)

    def test_crash_during_submission_is_recovered_as_unknown(self):
        self.approve()
        original = self.mailbox.send
        def crash(raw, thread):
            original(raw, thread)
            raise SystemExit('simulated crash after acceptance')
        self.mailbox.send = crash
        with self.assertRaises(SystemExit):
            self.flow.send(self.candidate)
        self.assertEqual(self.store.candidate(self.candidate)['state'], 'submitting')
        self.assertEqual(self.flow.reconcile(), [self.candidate])
        self.assertTrue(self.store.get('paused'))
        self.assertEqual(len(self.mailbox.messages()), 4)

    def test_organization_failure_never_resends_and_undo_preserves_other_labels(self):
        self.flow.edit(self.candidate, archive=True)
        self.approve()
        self.mailbox.modify('sales-1', ['personal-label'], [])
        self.mailbox.organization_fault = True
        self.assertEqual(self.flow.send(self.candidate), 'accepted_by_gmail')
        self.assertEqual(self.store.db.execute('SELECT state FROM organization').fetchone()[0], 'pending')
        self.mailbox.organization_fault = False
        self.assertEqual(self.flow.organize(self.candidate), 'done')
        self.assertNotIn('INBOX', self.mailbox.messages()[0].labels)
        self.assertEqual(self.flow.undo(self.run), [self.candidate])
        self.assertIn('INBOX', self.mailbox.messages()[0].labels)
        self.assertIn('personal-label', self.mailbox.messages()[0].labels)
        self.assertNotIn('uno reverse', self.mailbox.messages()[0].labels)
        self.assertEqual(len(self.mailbox.messages()), 4)

    def test_new_reply_before_send_invalidates_review(self):
        self.approve()
        self.mailbox.append(Message('new', 'thread-acme', 'sam@acme.example', 'Re: A quick demo?', 'Any thoughts?', self.time, '<new@acme.example>'))
        with self.assertRaisesRegex(ValueError, 'Thread changed'):
            self.flow.send(self.candidate)

    def test_new_reply_between_send_and_archive_stays_in_inbox(self):
        self.flow.edit(self.candidate, archive=True)
        self.approve()
        original = self.mailbox.send
        def reply_after_send(raw, thread):
            result = original(raw, thread)
            self.mailbox.append(Message('new', thread, 'sam@acme.example', 'Re: A quick demo?', 'Thanks!', self.time + 1, '<new@acme.example>'))
            return result
        self.mailbox.send = reply_after_send
        self.flow.send(self.candidate)
        self.assertIn('INBOX', next(m for m in self.mailbox.messages() if m.id == 'new').labels)
        self.assertNotIn('INBOX', self.mailbox.messages()[0].labels)

    def test_different_source_same_brand_deduplicated(self):
        self.approve()
        self.flow.send(self.candidate)
        self.time += 6
        self.mailbox.append(Message('sales-2', 'another-thread', 'other@acme.example', 'Demo', 'Book a demo — Acme', self.time, '<sales-2@acme.example>'))
        run = self.flow.scan(since=0)
        other = self.store.candidates(run)[0]['id']
        self.approve(other)
        with self.assertRaisesRegex(ValueError, 'Brand already'):
            self.flow.send(other)
        self.flow.scan(since=0)
        self.assertEqual(len(self.store.candidates()), 4)

    def test_two_processes_only_submit_once(self):
        self.approve()
        ctx = multiprocessing.get_context('spawn')
        queue = ctx.Queue()
        processes = [ctx.Process(target=competing_send, args=(str(self.root), self.candidate, self.time, queue)) for _ in range(2)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        results = [queue.get(timeout=2) for _ in processes]
        self.assertIn('accepted_by_gmail', results)
        self.assertEqual(len(self.mailbox.messages()), 4)

    def test_policy_sends_without_manual_approval_and_honors_watermark(self):
        preview = self.flow.policy_preview()
        pid = self.flow.enable_policy(preview, digest(preview))
        self.flow.tick()
        self.assertEqual(len(self.mailbox.messages()), 3)
        self.add_sales('future', self.time + 1)
        # Brand policy changes require explicit reactivation.
        preview = self.flow.policy_preview()
        pid = self.flow.enable_policy(preview, digest(preview))
        self.time += 2
        self.assertEqual(self.flow.tick(), ['accepted_by_gmail'])
        sent = next(c for c in self.store.candidates() if c['state'] == 'accepted_by_gmail')
        self.assertEqual(sent['policy_id'], pid)
        self.assertEqual(self.flow.tick(), [])

    def test_policy_backfill_daily_cap_and_local_day_rollover(self):
        self.add_sales()
        self.flow.scan(since=0)
        preview = self.flow.policy_preview(since=0, daily_cap=1, timezone='America/Los_Angeles')
        self.flow.enable_policy(preview, digest(preview))
        self.assertEqual(self.flow.tick(), ['accepted_by_gmail'])
        self.time += 6
        self.assertEqual(self.flow.tick(), [])
        self.time += 86400
        self.assertEqual(self.flow.tick(), ['accepted_by_gmail'])

    def test_policy_profile_edit_invalidates_queued_authorization(self):
        preview = self.flow.policy_preview(since=0)
        pid = self.flow.enable_policy(preview, digest(preview))
        c = self.store.candidate(self.candidate)
        self.store.db.execute("UPDATE candidates SET state='authorized',authorization=?,policy_id=? WHERE id=?", (digest(c['plan']), pid, c['id']))
        self.flow.set_profile(replace(self.profile, description='Changed.'))
        self.assertEqual(self.flow.tick(), [])
        with self.assertRaises(ValueError):
            self.flow.send(self.candidate)

    def test_policy_hours_and_pause(self):
        hour = __import__('datetime').datetime.fromtimestamp(self.time, __import__('datetime').timezone.utc).hour
        start = 0 if hour > 0 else 1
        preview = self.flow.policy_preview(since=0, start_hour=start, end_hour=start + 1)
        self.flow.enable_policy(preview, digest(preview))
        self.assertEqual(self.flow.tick(), [])
        self.flow.pause()
        self.assertEqual(self.flow.tick(), [])

    def test_policy_rejects_changed_preview_and_live_adapter(self):
        preview = self.flow.policy_preview()
        old_hash = digest(preview)
        preview['archive'] = True
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.flow.enable_policy(preview, old_hash)
        self.mailbox.synthetic = False
        with self.assertRaisesRegex(ValueError, 'synthetic'):
            self.flow.policy_preview()

    def test_reply_dedup_decline_suppression_and_inbox(self):
        self.approve()
        self.flow.send(self.candidate)
        self.mailbox.append(Message('reply', 'thread-acme', 'sam@acme.example', 'Re: Demo', 'Not interested, remove me.', self.time + 5, '<reply@acme.example>'))
        result = check_replies(self.flow)
        self.assertEqual(result[0]['category'], 'declined')
        self.assertEqual(check_replies(self.flow), [])
        self.assertTrue(self.store.db.execute("SELECT 1 FROM suppressions WHERE target='acme'").fetchone())
        self.assertIn('INBOX', next(m for m in self.mailbox.messages() if m.id == 'reply').labels)

    def test_mailbox_mismatch_is_rejected(self):
        self.mailbox.identity = 'other@demo.example'
        with self.assertRaisesRegex(ValueError, 'Mailbox mismatch'):
            Workflow(self.store, self.mailbox)


class ParsingTests(unittest.TestCase):
    def test_recipient_header_rules(self):
        self.assertEqual(address('Jane <jane@example.com>'), 'jane@example.com')
        for value in ['a@example.com, b@example.com', 'bad', 'a@example.com\r\nBcc: victim@example.com', '']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                address(value)

    def test_reply_to_authoritative(self):
        message = Message('1','1','sender@example.com','hi','body',0,'<1@example.com>', reply_to='reply@example.com')
        self.assertEqual(message.recipient, 'reply@example.com')
        message.reply_to = 'bad'
        with self.assertRaises(ValueError):
            _ = message.recipient

    def test_subject_mime_escaping_and_thread_validation(self):
        self.assertEqual(reply_subject('Re: RE: Héllo'), 'Re: Héllo')
        plan = {'recipient': 'person@example.com', 'subject': 'Re: Héllo', 'in_reply_to': '<1@example.com>', 'references': '<1@example.com>', 'body': '<script>alert("x")</script> café'}
        msg = BytesParser(policy=policy.default).parsebytes(mime(plan,'owner@example.com','<out@example.com>',0))
        self.assertIn('&lt;script&gt;', msg.get_body(preferencelist=('html',)).get_content())
        self.assertNotIn('<script>', msg.get_body(preferencelist=('html',)).get_content())
        message = Message('1','1','a@example.com','Hi','x',0,'bad')
        with self.assertRaises(ValueError):
            threading(message)

    def test_classifier_suite_and_protected_overrides(self):
        self.assertTrue(classifier.evaluate()['passed'])
        for text in ['password','invoice','support ticket','newsletter','job application']:
            m = Message('1','1','seller@acme.example','Hello',text+' book a demo Acme',0,'<1@acme.example>')
            result = classifier.classify(m,[m],'me@example.com',{'acme.example':{'id':'acme','name':'Acme'}})
            self.assertFalse(result.automatic)
            self.assertEqual(result.category,'excluded')

    def test_reply_quotes_and_auto_response_not_interest(self):
        message = Message('1','1','person@example.com','Re: hi','Thanks\n> I am interested',0,'<1@example.com>')
        self.assertEqual(classify_reply(message)[0], 'substantive_other')
        message.body='I am interested'
        message.headers={'Auto-Submitted':'auto-replied'}
        self.assertEqual(classify_reply(message)[0], 'automated_acknowledgement')

    def test_profile_rejects_unsafe_cta(self):
        for cta in ['javascript:alert(1)', 'http://example.com', 'https://user:secret@example.com']:
            with self.assertRaises(ValueError):
                Profile('Acme','acme.example','Description',cta,'Alex')
