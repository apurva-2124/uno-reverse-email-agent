"""Shared manual/policy authorization and durable submission state machine."""
from dataclasses import asdict
from datetime import datetime
import json
from uuid import uuid4
from zoneinfo import ZoneInfo
from . import classifier, composer
from .mailbox import BeforeSubmissionError, MailboxAdapter
from .models import Profile, canonical, digest, now
from .storage import Store


class Workflow:
    def __init__(self, store: Store, mailbox: MailboxAdapter, clock=now):
        self.store, self.mailbox, self.clock = store, mailbox, clock
        identity = store.get("mailbox")
        if identity and identity != mailbox.identity:
            raise ValueError("Mailbox mismatch; use a separate state directory")
        store.set("mailbox", mailbox.identity)

    @property
    def profile(self):
        value = self.store.get("profile")
        if not value:
            raise ValueError("Configure and approve a profile first")
        return Profile(**value)

    def set_profile(self, profile: Profile):
        with self.store.transaction() as db:
            self.store.set("profile", asdict(profile))
            db.execute("UPDATE policies SET active=0")
            db.execute("UPDATE candidates SET authorization=NULL,policy_id=NULL,state='needs_review' WHERE state IN ('ready','authorized','needs_review')")

    def set_brands(self, brands):
        if not isinstance(brands, dict):
            raise ValueError("Brands must map sender domains to id/name objects")
        for domain, brand in brands.items():
            if not isinstance(domain, str) or not isinstance(brand, dict):
                raise ValueError("Invalid brand mapping")
            if not all(isinstance(brand.get(k), str) and 0 < len(brand[k]) <= 200 for k in ("id", "name")):
                raise ValueError("Each brand needs a stable id and display name")
        with self.store.transaction() as db:
            self.store.set("brands", brands)
            db.execute("UPDATE policies SET active=0")
            db.execute("UPDATE candidates SET authorization=NULL,policy_id=NULL,state='needs_review' WHERE state IN ('ready','authorized','needs_review')")

    def scan(self, since=None, archive=False):
        since = self.clock() - 7 * 86400 if since is None else since
        profile = self.profile
        run = uuid4().hex[:12]
        messages = self.mailbox.scan(since)
        self.store.db.execute("INSERT INTO runs VALUES(?,?,?)", (run, self.clock(), canonical({"since": since, "inbox": True, "count": len(messages)})))
        for message in messages:
            thread = self.mailbox.thread(message.thread_id)
            decision = classifier.classify(message, thread, self.mailbox.identity, self.store.get("brands", {}))
            plan = {"source_id": message.id, "thread_id": message.thread_id,
                    "source_hash": message.fingerprint, "source_time": message.received_at,
                    "captured_ids": sorted(m.id for m in thread), "profile_version": profile.version,
                    "brand": decision.brand, "company": decision.company, "reason": decision.reason,
                    "evidence": decision.evidence, "category": decision.category, "automatic": decision.automatic,
                    "classifier": classifier.VERSION, "template": composer.TEMPLATE_VERSION,
                    "archive": bool(archive), "mailbox": self.mailbox.identity}
            state = "ready" if decision.category == "sales" else decision.category
            if decision.category != "excluded":
                try:
                    reply, refs = composer.threading(message)
                    plan.update(recipient=message.recipient, subject=composer.reply_subject(message.subject),
                                body=composer.draft(profile, decision.company or "there"), in_reply_to=reply, references=refs)
                except ValueError as exc:
                    plan["reason"] = str(exc)
                    state = "excluded"
            self.store.db.execute("INSERT OR IGNORE INTO candidates VALUES(?,?,?,?,?,?,?)",
                                  (uuid4().hex[:12], run, message.id, canonical(plan), state, None, None))
        return run

    def edit(self, candidate_id, body=None, company=None, brand=None, archive=None):
        with self.store.transaction() as db:
            candidate = self.store.candidate(candidate_id)
            if candidate["state"] not in {"ready", "needs_review", "authorized"}:
                raise ValueError("Candidate cannot be edited in its current state")
            plan = candidate["plan"]
            if body is not None:
                if not isinstance(body, str) or not body.strip() or len(body) > 10000:
                    raise ValueError("Body must be 1–10000 characters")
                plan["body"] = body
            for key, value in (("company", company), ("brand", brand)):
                if value is not None:
                    if not isinstance(value, str) or not value.strip() or len(value) > 200:
                        raise ValueError("Company and brand must be 1–200 characters")
                    plan[key] = value.strip()
            if archive is not None:
                if not isinstance(archive, bool):
                    raise ValueError("Archive must be true or false")
                plan["archive"] = archive
            plan["automatic"] = False
            db.execute("UPDATE candidates SET plan=?,authorization=NULL,policy_id=NULL,state='needs_review' WHERE id=?",
                       (canonical(plan), candidate_id))

    def redraft(self, candidate_id):
        with self.store.transaction() as db:
            c = self.store.candidate(candidate_id)
            if c["state"] not in {"ready", "needs_review", "authorized"}:
                raise ValueError("Submitted or excluded candidates cannot be redrafted")
            plan = c["plan"]
            thread = self.mailbox.thread(plan["thread_id"])
            source = next((m for m in thread if m.id == plan["source_id"]), None)
            if source is None:
                raise ValueError("Source message no longer exists")
            result = classifier.classify(source, thread, self.mailbox.identity, self.store.get("brands", {}))
            if result.category == "excluded":
                raise ValueError("Source now matches a deterministic exclusion")
            reply, refs = composer.threading(source)
            plan.update(source_hash=source.fingerprint, captured_ids=sorted(m.id for m in thread),
                        profile_version=self.profile.version, body=composer.draft(self.profile, result.company or "there"),
                        recipient=source.recipient, subject=composer.reply_subject(source.subject),
                        brand=result.brand, company=result.company, category=result.category, reason=result.reason,
                        evidence=result.evidence, in_reply_to=reply, references=refs, automatic=False)
            db.execute("UPDATE candidates SET plan=?,state='needs_review',authorization=NULL,policy_id=NULL WHERE id=?",
                       (canonical(plan), candidate_id))

    def approve(self, candidate_id, expected_hash):
        with self.store.transaction() as db:
            c = self.store.candidate(candidate_id)
            if c["state"] not in {"ready", "needs_review", "authorized"}:
                raise ValueError("Candidate is not reviewable")
            plan = c["plan"]
            if expected_hash != digest(plan):
                raise ValueError("Draft changed; review the new exact content")
            if not plan.get("brand") or not plan.get("company") or not plan.get("body"):
                raise ValueError("Confirm the company and stable brand identity before approval")
            if plan["profile_version"] != self.profile.version:
                raise ValueError("Profile changed; redraft before approval")
            db.execute("UPDATE candidates SET state='authorized',authorization=?,policy_id=NULL WHERE id=?",
                       (digest(plan), candidate_id))

    def exclude(self, candidate_id):
        with self.store.transaction() as db:
            c = self.store.candidate(candidate_id)
            if c["state"] not in {"ready", "needs_review", "authorized", "excluded"}:
                raise ValueError("Submitted candidates cannot be excluded")
            db.execute("UPDATE candidates SET state='excluded',authorization=NULL,policy_id=NULL WHERE id=?", (candidate_id,))

    def suppress(self, target, reason="User suppression"):
        self.store.db.execute("INSERT OR REPLACE INTO suppressions VALUES(?,?)", (target, reason))

    def pause(self, reason="User paused"):
        self.store.set("paused", reason)

    def resume(self):
        if self.store.db.execute("SELECT 1 FROM attempts WHERE state IN ('submitting','send_unknown')").fetchone():
            raise ValueError("Reconcile unresolved sends before resuming")
        self.store.set("paused", None)

    def _fresh(self, plan):
        if self.mailbox.identity != plan["mailbox"] or self.store.get("mailbox") != plan["mailbox"]:
            raise ValueError("Mailbox identity changed")
        if plan["profile_version"] != self.profile.version:
            raise ValueError("Profile changed after drafting")
        if self.store.db.execute("SELECT 1 FROM suppressions WHERE target IN (?,?)", (plan["brand"], plan["recipient"])).fetchone():
            raise ValueError("Recipient or brand is suppressed")
        thread = self.mailbox.thread(plan["thread_id"])
        if sorted(m.id for m in thread) != plan["captured_ids"]:
            raise ValueError("Thread changed; new review is required")
        source = next((m for m in thread if m.id == plan["source_id"]), None)
        if source is None or source.fingerprint != plan["source_hash"]:
            raise ValueError("Source changed since review")
        result = classifier.classify(source, thread, self.mailbox.identity, self.store.get("brands", {}))
        if result.category == "excluded":
            raise ValueError("Source now matches a deterministic exclusion")
        return result

    def policy_preview(self, *, since=None, archive=False, daily_cap=25, run_cap=10,
                       timezone="UTC", start_hour=0, end_hour=24):
        if not self.mailbox.synthetic or not classifier.evaluate()["passed"]:
            raise ValueError("This classifier is approved for synthetic mailboxes only")
        ZoneInfo(timezone)
        if not (1 <= daily_cap <= 25 and 1 <= run_cap <= 10 and 0 <= start_hour < end_hour <= 24):
            raise ValueError("Invalid caps or sending hours")
        profile = self.profile
        return {"mailbox": self.mailbox.identity, "profile_version": profile.version,
                "brands_version": digest(self.store.get("brands", {})), "template": composer.TEMPLATE_VERSION,
                "classifier": classifier.VERSION, "scope": "inbox", "since": since,
                "archive": bool(archive), "daily_cap": daily_cap, "run_cap": run_cap,
                "timezone": timezone, "start_hour": start_hour, "end_hour": end_hour,
                "poll_seconds": 900, "example": composer.draft(profile, "Example"),
                "profile": asdict(profile), "synthetic_only": True}

    def enable_policy(self, preview, expected_hash):
        current = self.policy_preview(**{k: preview[k] for k in ("since", "archive", "daily_cap", "run_cap", "timezone", "start_hour", "end_hour")})
        if digest(preview) != expected_hash or current != preview:
            raise ValueError("Policy changed; review the current preview")
        with self.store.transaction() as db:
            if self.store.get("paused"):
                raise ValueError("Resume the paused mailbox explicitly before activation")
            policy = dict(preview, activated=self.clock())
            policy["since"] = self.clock() if policy["since"] is None else policy["since"]
            policy_id = digest(policy)
            db.execute("UPDATE policies SET active=0")
            db.execute("INSERT INTO policies VALUES(?,?,1)", (policy_id, canonical(policy)))
            return policy_id

    def active_policy(self):
        row = self.store.db.execute("SELECT id,value FROM policies WHERE active=1").fetchone()
        return (row[0], json.loads(row[1])) if row else (None, None)

    def _policy_valid(self, policy_id, plan):
        active_id, policy = self.active_policy()
        if active_id != policy_id or not policy:
            raise ValueError("Policy is no longer active")
        if (not self.mailbox.synthetic or policy["profile_version"] != self.profile.version
                or policy["brands_version"] != digest(self.store.get("brands", {}))
                or policy["classifier"] != classifier.VERSION or policy["template"] != composer.TEMPLATE_VERSION
                or plan["source_time"] < policy["since"] or plan["archive"] != policy["archive"]
                or not plan["automatic"] or plan["body"] != composer.draft(self.profile, plan["company"])):
            raise ValueError("Policy no longer authorizes this candidate")
        hour = datetime.fromtimestamp(self.clock(), ZoneInfo(policy["timezone"])).hour
        if not policy["start_hour"] <= hour < policy["end_hour"]:
            raise ValueError("Outside approved sending hours")
        return policy

    def tick(self):
        policy_id, policy = self.active_policy()
        if not policy or self.store.get("paused"):
            return []
        # Rescan approved scope: stable source IDs are the cursor/dedup authority.
        self.scan(policy["since"], policy["archive"])
        sent = []
        for c in self.store.candidates():
            if len(sent) >= policy["run_cap"] or self.store.get("paused"):
                break
            if c["state"] not in {"ready", "authorized"} or not c["plan"].get("automatic"):
                continue
            if c["state"] == "authorized" and c["policy_id"] != policy_id:
                continue
            try:
                self._policy_valid(policy_id, c["plan"])
                self.store.db.execute("UPDATE candidates SET state='authorized',authorization=?,policy_id=? WHERE id=? AND state='ready'",
                                      (digest(c["plan"]), policy_id, c["id"]))
                sent.append(self.send(c["id"]))
            except ValueError:
                continue
        self.store.set("last_poll", self.clock())
        return sent

    def send(self, candidate_id):
        if not self.mailbox.synthetic:
            raise ValueError("Live-mail submission is disabled in this development milestone")
        with self.store.sender_lock():
            self._recover_interrupted()
            c = self.store.candidate(candidate_id)
            existing = self.store.db.execute("SELECT state FROM attempts WHERE candidate=?", (candidate_id,)).fetchone()
            if existing and existing[0] != "failed_before_send":
                return existing[0]
            if c["state"] != "authorized" or c["authorization"] != digest(c["plan"]):
                raise ValueError("Exact current draft is not authorized")
            plan = c["plan"]
            decision = self._fresh(plan)
            limits = {"daily_cap": 25, "run_cap": 10, "timezone": self.store.get("timezone", "UTC")}
            if c["policy_id"]:
                limits = self._policy_valid(c["policy_id"], plan)
                if not decision.automatic or decision.brand != plan["brand"]:
                    raise ValueError("Candidate no longer meets automatic classification")
            timestamp = self.clock()
            day = datetime.fromtimestamp(timestamp, ZoneInfo(limits["timezone"])).date().isoformat()
            message_id = f"<{uuid4().hex}@uno-reverse.local>"
            raw = composer.mime(plan, self.mailbox.identity, message_id, timestamp)
            with self.store.transaction() as db:
                if self.store.get("paused"):
                    raise ValueError("Mailbox is paused")
                # Recheck durable authorization and policy under the write transaction.
                fresh = self.store.candidate(candidate_id)
                if fresh["authorization"] != c["authorization"] or fresh["plan"] != plan or fresh["state"] != "authorized" or fresh["policy_id"] != c["policy_id"]:
                    raise ValueError("Authorization changed")
                if c["policy_id"]:
                    self._policy_valid(c["policy_id"], plan)
                if db.execute("SELECT 1 FROM suppressions WHERE target IN (?,?)", (plan["brand"], plan["recipient"])).fetchone():
                    raise ValueError("Recipient or brand is suppressed")
                daily = db.execute("SELECT COUNT(*) FROM attempts WHERE day=? AND state!='failed_before_send'", (day,)).fetchone()[0]
                per_run = db.execute("SELECT COUNT(*) FROM attempts a JOIN candidates c ON c.id=a.candidate WHERE c.run_id=? AND a.state!='failed_before_send'", (c["run_id"],)).fetchone()[0]
                if daily >= limits["daily_cap"] or per_run >= limits["run_cap"]:
                    raise ValueError("Sending cap reached")
                last = self.store.get("last_submission")
                if last is not None and timestamp - last < 5:
                    raise ValueError("Wait at least five seconds between submissions")
                reservation = db.execute("SELECT candidate FROM reservations WHERE brand=?", (plan["brand"],)).fetchone()
                if reservation and reservation[0] != candidate_id:
                    raise ValueError("Brand already reserved or contacted")
                db.execute("INSERT OR IGNORE INTO reservations VALUES(?,?)", (plan["brand"], candidate_id))
                db.execute("INSERT OR REPLACE INTO attempts VALUES(?,?,?,?,?,?,?,?)",
                           (candidate_id, message_id, raw, "submitting", timestamp, day, None,
                            digest({"plan_hash": c["authorization"], "policy_id": c["policy_id"], "mode": "policy" if c["policy_id"] else "manual"})))
                self.store.set("last_submission", timestamp)
                db.execute("UPDATE candidates SET state='submitting' WHERE id=?", (candidate_id,))
            try:
                provider_id = self.mailbox.send(raw, plan["thread_id"])
                if not isinstance(provider_id, str) or not provider_id:
                    raise RuntimeError("Ambiguous adapter response")
            except BeforeSubmissionError:
                self._state(candidate_id, "failed_before_send")
                self.store.db.execute("UPDATE candidates SET state='authorized' WHERE id=?", (candidate_id,))
                return "failed_before_send"
            except Exception:
                self._state(candidate_id, "send_unknown")
                self.pause("Unresolved send; reconcile before resuming")
                return "send_unknown"
            self._state(candidate_id, "accepted_by_gmail", provider_id)
            self.organize(candidate_id)
            return "accepted_by_gmail"

    def _state(self, candidate_id, state, provider_id=None):
        with self.store.transaction() as db:
            db.execute("UPDATE attempts SET state=?,provider_id=COALESCE(?,provider_id) WHERE candidate=?", (state, provider_id, candidate_id))
            db.execute("UPDATE candidates SET state=? WHERE id=?", (state, candidate_id))

    def _recover_interrupted(self):
        interrupted = self.store.db.execute("SELECT candidate FROM attempts WHERE state='submitting'").fetchall()
        for row in interrupted:
            self._state(row[0], "send_unknown")
        if interrupted:
            self.pause("Interrupted submission; reconciliation required")

    def reconcile(self):
        recovered = []
        with self.store.sender_lock():
            self._recover_interrupted()
            for attempt in self.store.db.execute("SELECT * FROM attempts WHERE state='send_unknown'").fetchall():
                plan = self.store.candidate(attempt["candidate"])["plan"]
                provider_id = self.mailbox.find_sent(attempt["message_id"], plan["recipient"], plan["thread_id"])
                if provider_id:
                    self._state(attempt["candidate"], "accepted_by_gmail", provider_id)
                    self.organize(attempt["candidate"])
                    recovered.append(attempt["candidate"])
        return recovered

    def organize(self, candidate_id):
        # Each label delta is durable before mutation; retries never submit mail.
        from .organization import organize
        return organize(self, candidate_id)

    def undo(self, run_id):
        from .organization import undo
        return undo(self, run_id)
