"""Incremental synthetic reply observation. Does not send responses."""
import re
from .models import address
from .organization import LABEL


def classify_reply(message):
    headers = {k.lower(): v for k, v in message.headers.items()}
    # Never use quoted original pitches as evidence of interest.
    lines = []
    for line in message.body.splitlines():
        if re.match(r"\s*(>|On .+wrote:|[-]+\s*Original Message)", line, re.I):
            break
        lines.append(line)
    text = "\n".join(lines).strip()
    if headers.get("auto-submitted", "no").lower() != "no":
        return "automated_acknowledgement", text[:240]
    if re.search(r"out of (?:the )?office|on vacation", text, re.I):
        return "out_of_office", text[:240]
    if re.search(r"not monitored|unmonitored mailbox", text, re.I):
        return "unmonitored_mailbox", text[:240]
    if re.search(r"not interested|unsubscribe|remove me|stop emailing|opt out", text, re.I):
        return "declined", text[:240]
    if re.search(r"(?:I'm|I am|we are|we're) interested|let's (?:chat|talk)|sounds interesting", text, re.I):
        return "interested", text[:240]
    return ("substantive_other" if text else "uncertain"), text[:240]


def check_replies(workflow):
    store, mailbox = workflow.store, workflow.mailbox
    notifications = []
    for attempt in store.db.execute("SELECT * FROM attempts WHERE state='accepted_by_gmail'").fetchall():
        plan = store.candidate(attempt["candidate"])["plan"]
        for message in mailbox.thread(plan["thread_id"]):
            if message.received_at <= attempt["submitted"] or "SENT" in message.labels:
                continue
            try:
                if address(message.sender) == mailbox.identity:
                    continue
            except ValueError:
                continue
            category, evidence = classify_reply(message)
            with store.transaction() as db:
                result = db.execute("INSERT OR IGNORE INTO replies VALUES(?,?,?,?,?)", (message.id, attempt["candidate"], category, message.received_at, evidence))
                if category == "declined":
                    workflow.suppress(plan["recipient"], "Decline or opt-out")
                    workflow.suppress(plan["brand"], "Decline or opt-out")
            # Idempotent label application also retries on subsequent checks.
            try:
                mailbox.modify(message.id, [LABEL], [])
            except Exception:
                pass
            if result.rowcount and category in {"interested", "declined", "substantive_other", "uncertain"}:
                notifications.append({"message_id": message.id, "category": category, "evidence": evidence})
    return notifications
