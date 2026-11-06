#!/usr/bin/env python3
"""Local policy/send ledger. No network, model calls, scheduler, or mail credentials."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from email import policy as email_policy
from email.parser import HeaderParser
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

TEMPLATE_VERSION = "reverse-pitch-v1"
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS policies(hash TEXT PRIMARY KEY,config TEXT NOT NULL,activated REAL NOT NULL,consent TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,policy TEXT NOT NULL,started REAL NOT NULL,ended REAL);
CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY,run TEXT NOT NULL,brand TEXT UNIQUE NOT NULL,source TEXT UNIQUE NOT NULL,recipient TEXT NOT NULL,plan TEXT NOT NULL,policy TEXT NOT NULL,created REAL NOT NULL,day TEXT NOT NULL,state TEXT NOT NULL,provider_id TEXT);
CREATE TABLE IF NOT EXISTS suppressions(target TEXT PRIMARY KEY,reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(key TEXT PRIMARY KEY,data TEXT NOT NULL,created REAL NOT NULL);
"""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text(value, name, maximum=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or '\x00' in value:
        raise ValueError(f"{name} must be a nonempty string of at most {maximum} characters")
    return value


def email(value):
    text(value, "email", 320)
    if any(c in value for c in '\r\n'):
        raise ValueError("Invalid email header")
    h = HeaderParser(policy=email_policy.default).parsestr(f'To: {value}\n\n')['To']
    if h.defects or len(h.addresses) != 1:
        raise ValueError("Exactly one valid email address required")
    a = h.addresses[0]
    if not a.username or not a.domain or '.' not in a.domain or not re.fullmatch(r'[A-Za-z0-9.-]+', a.domain):
        raise ValueError("Invalid email address")
    return a.addr_spec.lower()


def https(value):
    text(value, 'URL')
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or re.search(r'\s', value):
        raise ValueError("Use an HTTPS URL without credentials or whitespace")
    return value


def config(value):
    allowed = {'mailbox','profile','brandvault_choice','invitation','archive','timezone','daily_cap','run_cap','interval_minutes','start_hour','end_hour','backfill_since'}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError("Unknown configuration fields")
    c = dict(value)
    c['mailbox'] = email(c['mailbox'])
    p = c['profile']
    if not isinstance(p, dict) or set(p) != {'business','description','cta','signature','source','source_version'}:
        raise ValueError("Profile requires business, description, cta, signature, source, source_version")
    for key, v in p.items():
        text(v, key)
    https(p['cta'])
    if p['source'] not in {'manual','brandvault'}:
        raise ValueError("Unknown profile source")
    c.setdefault('brandvault_choice', 'local')
    if c['brandvault_choice'] not in {'local','existing','create'}:
        raise ValueError("Unknown BrandVault preference")
    c.setdefault('invitation', {'enabled': False, 'text': ''})
    invite = c['invitation']
    if not isinstance(invite, dict) or set(invite) != {'enabled','text'} or type(invite['enabled']) is not bool or not isinstance(invite['text'], str):
        raise ValueError("Invitation needs enabled boolean and text")
    if invite['enabled']:
        text(invite['text'], 'invitation', 1000)
        urls = re.findall(r'https://[^\s]+', invite['text'])
        if len(urls) != 1 or urlparse(urls[0]).hostname not in {'optimly.ai','app.optimly.ai'}:
            raise ValueError("Invitation must contain one verified official Optimly URL")
        https(urls[0])
    elif invite['text']:
        raise ValueError("Disabled invitation must have empty text")
    defaults = {'archive':False,'timezone':'UTC','daily_cap':25,'run_cap':10,'interval_minutes':15,'start_hour':0,'end_hour':24,'backfill_since':None}
    for key, default in defaults.items():
        c.setdefault(key, default)
    if type(c['archive']) is not bool:
        raise ValueError("Archive must be boolean")
    ZoneInfo(c['timezone'])
    for key, lower, upper in [('daily_cap',1,25),('run_cap',1,10),('interval_minutes',1,1440),('start_hour',0,23),('end_hour',1,24)]:
        if type(c[key]) is not int or not lower <= c[key] <= upper:
            raise ValueError(f"{key} outside supported range {lower}–{upper}")
    if c['start_hour'] >= c['end_hour']:
        raise ValueError("End hour must be later than start hour")
    if c['backfill_since'] is not None and (type(c['backfill_since']) not in {int,float} or not 0 <= c['backfill_since'] <= time.time()):
        raise ValueError("Backfill must be an explicit past Unix timestamp")
    return c


def render(c, company):
    text(company, 'company', 200)
    if any(ch in company for ch in '\r\n') or re.search(r'https?://|www\.|@|[<>]', company, re.I):
        raise ValueError("Company must be one line")
    p = c['profile']
    body = (f"Hi {company} team,\n\nThanks for reaching out — a little reverse pitch in return!\n\n"
            f"{p['business']}: {p['description']}\n\nIf that sounds useful: {p['cta']}")
    if c['invitation']['enabled']:
        body += '\n\n' + c['invitation']['text']
    return body + '\n\n' + p['signature']


class Ledger:
    def __init__(self, path, create=False, clock=time.time):
        self.root = Path(path).expanduser().resolve()
        self.clock = clock
        if not create and not (self.root / 'ledger.sqlite3').exists():
            raise ValueError("Ledger missing; configure explicitly, never initialize during an automatic run")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        target = self.root / 'ledger.sqlite3'
        fd = os.open(target, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(target, 0o600)
        self.db = sqlite3.connect(target, timeout=20, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def get(self, key, default=None):
        row = self.db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (key, canonical(value)))

    def configure(self, value):
        c = config(value)
        with self.transaction():
            old = self.get('config')
            if old and old['mailbox'] != c['mailbox']:
                raise ValueError("Mailbox cannot change in an existing ledger")
            if self.get('open_run'):
                raise ValueError("End the active run before reconfiguring")
            self.put('config', c)
            self.put('active', None)
        return self.preview()

    def preview(self):
        c = self.get('config')
        if not c:
            raise ValueError("No profile configured")
        policy = {'config':c,'template_version':TEMPLATE_VERSION,'example':render(c,'Example Company')}
        return dict(policy, hash=digest(policy))

    def activate(self, expected_hash, consent):
        text(consent, 'activation statement')
        with self.transaction():
            p = self.preview()
            if p['hash'] != expected_hash or self.get('open_run'):
                raise ValueError("Policy changed or a run is active; review the current preview")
            # Activation watermark is distinct from the stable preview hash.
            activated = self.clock()
            policy_id = digest({'preview':expected_hash,'activated':activated,'nonce':uuid4().hex})
            self.db.execute('INSERT INTO policies VALUES(?,?,?,?)', (policy_id, canonical(p), activated, consent))
            self.put('active', policy_id)
        return {'active':policy_id,'paused':self.get('paused')}

    def policy(self):
        row = self.db.execute('SELECT * FROM policies WHERE hash=?', (self.get('active'),)).fetchone()
        if not row:
            raise ValueError("No active policy")
        p = json.loads(row['config'])
        if p != self.preview():
            raise ValueError("Stored policy no longer matches config/template")
        c = p['config']
        return row['hash'], c, c['backfill_since'] if c['backfill_since'] is not None else row['activated']

    def begin(self, run):
        text(run, 'run ID', 200)
        with self.transaction():
            pid, _, _ = self.policy()
            if self.get('paused') or self.get('open_run'):
                raise ValueError("Mailbox is paused or another run is open")
            self.db.execute('INSERT INTO runs VALUES(?,?,?,NULL)', (run,pid,self.clock()))
            self.put('open_run', run)
        return {'run':run,'policy':pid}

    def reserve(self, run, candidate):
        required = {'brand','company','recipient','source_id','thread_id','source_message_ids','source_received_at','subject','evidence'}
        if not isinstance(candidate, dict) or set(candidate) != required:
            raise ValueError("Candidate fields do not match the documented schema")
        c = dict(candidate)
        for key in required - {'source_received_at','source_message_ids'}:
            text(c[key], key)
        c['recipient'] = email(c['recipient'])
        c['brand'] = c['brand'].strip().casefold()
        if re.search(r'no[._-]?reply|mailer-daemon|postmaster', c['recipient'].split('@')[0]):
            raise ValueError("Unmonitored recipient")
        if '\n' in c['subject'] or '\r' in c['subject']:
            raise ValueError("Invalid subject")
        if not isinstance(c['source_message_ids'], list) or c['source_id'] not in c['source_message_ids'] or not all(isinstance(i,str) and i for i in c['source_message_ids']):
            raise ValueError("Capture actual source message IDs")
        with self.transaction():
            pid, cfg, since = self.policy()
            if self.get('paused') or self.get('open_run') != run:
                raise ValueError("Paused or run lock not held")
            t = self.clock()
            if type(c['source_received_at']) not in {int,float} or not since <= c['source_received_at'] <= t + 300:
                raise ValueError("Source is outside approved scope")
            if c['recipient'] == cfg['mailbox']:
                raise ValueError("Self-send excluded")
            if self.db.execute('SELECT 1 FROM suppressions WHERE target IN (?,?)', (c['brand'],c['recipient'])).fetchone():
                raise ValueError("Suppressed recipient or brand")
            local = datetime.fromtimestamp(t, ZoneInfo(cfg['timezone']))
            if not cfg['start_hour'] <= local.hour < cfg['end_hour']:
                raise ValueError("Outside approved hours")
            day = local.date().isoformat()
            daily = self.db.execute('SELECT COUNT(*) FROM attempts WHERE day=?', (day,)).fetchone()[0]
            per_run = self.db.execute('SELECT COUNT(*) FROM attempts WHERE run=?', (run,)).fetchone()[0]
            if daily >= cfg['daily_cap'] or per_run >= cfg['run_cap']:
                raise ValueError("Sending cap reached")
            last = self.get('last_reservation')
            if last is not None and t-last < 5:
                raise ValueError("Wait at least five seconds between submissions")
            plan = dict(c, body=render(cfg,c['company']), mailbox=cfg['mailbox'], archive=cfg['archive'], label='uno reverse', policy=pid)
            attempt = uuid4().hex
            try:
                self.db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?,NULL)',
                                (attempt,run,c['brand'],c['source_id'],c['recipient'],canonical(plan),pid,t,day,'reserved'))
            except sqlite3.IntegrityError:
                raise ValueError("Brand/source already reserved; do not send") from None
            self.put('last_reservation', t)
            return {'attempt':attempt, 'plan':plan, 'receipt_hash':digest(plan)}

    def result(self, attempt, outcome, provider_id=None):
        if outcome not in {'accepted','unknown'}:
            raise ValueError("Unsupported result; reservations cannot be released automatically")
        if outcome == 'accepted':
            text(provider_id, 'provider ID', 500)
        with self.transaction():
            row = self.db.execute('SELECT * FROM attempts WHERE id=?',(attempt,)).fetchone()
            if not row:
                raise ValueError("Attempt missing")
            if row['state'] == 'accepted':
                if outcome != 'accepted' or provider_id != row['provider_id']:
                    raise ValueError("Accepted outcome is immutable")
                return {'state':'accepted'}
            self.db.execute('UPDATE attempts SET state=?,provider_id=? WHERE id=?',(outcome,provider_id,attempt))
            if outcome == 'unknown':
                self.put('paused','Unresolved submission; reconcile then explicitly resume')
        return {'state':outcome}

    def end(self, run, scanned_through=None):
        with self.transaction():
            if self.get('open_run') != run:
                raise ValueError("Run is not open")
            unknown = self.db.execute("SELECT 1 FROM attempts WHERE run=? AND state IN ('reserved','unknown')",(run,)).fetchone()
            if unknown:
                self.db.execute("UPDATE attempts SET state='unknown' WHERE run=? AND state='reserved'",(run,))
                self.put('paused','Run ended with unresolved submissions')
            if scanned_through is not None:
                if not 0 <= scanned_through <= self.clock():
                    raise ValueError("Invalid scan boundary")
                self.put('last_scan',max(self.get('last_scan',0),scanned_through))
            self.db.execute('UPDATE runs SET ended=? WHERE id=?',(self.clock(),run))
            self.put('open_run',None)
        return {'paused':self.get('paused')}

    def pause(self, reason):
        self.put('paused',text(reason,'pause reason'))

    def resume(self, consent):
        text(consent,'resume statement')
        with self.transaction():
            self.policy()
            if self.get('open_run') or self.db.execute("SELECT 1 FROM attempts WHERE state IN ('reserved','unknown')").fetchone():
                raise ValueError("Close the old run and reconcile unresolved submissions before resuming")
            self.put('resume_consent',consent)
            self.put('paused',None)

    def suppress(self, target, reason):
        target = text(target,'target').strip()
        target = email(target) if '@' in target else target.casefold()
        self.db.execute('INSERT OR REPLACE INTO suppressions VALUES(?,?)',(target,text(reason,'reason')))

    def event(self, key, data):
        raw = canonical(data)
        if len(raw) > 16000:
            raise ValueError("Keep event data minimal; do not store full incoming bodies")
        result = self.db.execute('INSERT OR IGNORE INTO events VALUES(?,?,?)',(text(key,'event key'),raw,self.clock()))
        return {'new':bool(result.rowcount)}

    def status(self):
        effective_since = None
        if self.get('active'):
            _, _, effective_since = self.policy()
        return {'policy':self.get('active'),'paused':self.get('paused'),'open_run':self.get('open_run'),
                'effective_since':effective_since,'last_scan':self.get('last_scan'),
                'attempts':[dict(r) for r in self.db.execute('SELECT * FROM attempts')],
                'suppressions':[dict(r) for r in self.db.execute('SELECT * FROM suppressions')],
                'events':[dict(r) for r in self.db.execute('SELECT * FROM events')]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',required=True,type=Path)
    sub = parser.add_subparsers(dest='command',required=True)
    for command in ('configure','reserve','event'):
        p = sub.add_parser(command)
        p.add_argument('--input',required=True,type=Path)
        if command == 'reserve': p.add_argument('--run',required=True)
        if command == 'event': p.add_argument('--key',required=True)
    for command in ('status','policy'): sub.add_parser(command)
    p = sub.add_parser('activate'); p.add_argument('--hash',required=True); p.add_argument('--consent',required=True)
    p = sub.add_parser('begin-run'); p.add_argument('--run',required=True)
    p = sub.add_parser('end-run'); p.add_argument('--run',required=True); p.add_argument('--scanned-through',type=float)
    p = sub.add_parser('result'); p.add_argument('--attempt',required=True); p.add_argument('--outcome',choices=['accepted','unknown'],required=True); p.add_argument('--provider-id')
    p = sub.add_parser('pause'); p.add_argument('--reason',default='User paused')
    p = sub.add_parser('resume'); p.add_argument('--consent',required=True)
    p = sub.add_parser('suppress'); p.add_argument('--target',required=True); p.add_argument('--reason',required=True)
    args = parser.parse_args()
    ledger = None
    try:
        ledger = Ledger(args.state,create=args.command=='configure')
        data = json.loads(args.input.read_text()) if hasattr(args,'input') else None
        if args.command == 'configure': result = ledger.configure(data)
        elif args.command == 'reserve': result = ledger.reserve(args.run,data)
        elif args.command == 'event': result = ledger.event(args.key,data)
        elif args.command == 'status': result = ledger.status()
        elif args.command == 'policy': result = ledger.preview()
        elif args.command == 'activate': result = ledger.activate(args.hash,args.consent)
        elif args.command == 'begin-run': result = ledger.begin(args.run)
        elif args.command == 'end-run': result = ledger.end(args.run,args.scanned_through)
        elif args.command == 'result': result = ledger.result(args.attempt,args.outcome,args.provider_id)
        elif args.command == 'pause': result = ledger.pause(args.reason)
        elif args.command == 'resume': result = ledger.resume(args.consent)
        elif args.command == 'suppress': result = ledger.suppress(args.target,args.reason)
        print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
        print(f'ledger: {exc}',file=sys.stderr)
        return 2
    finally:
        if ledger: ledger.close()


if __name__ == '__main__':
    raise SystemExit(main())
