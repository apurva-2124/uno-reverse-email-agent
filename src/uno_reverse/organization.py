"""Recoverable organization deltas, independent of send attempts."""
import json
from .models import canonical

LABEL = "uno reverse"


def organize(workflow, candidate_id):
    store, mailbox = workflow.store, workflow.mailbox
    attempt = store.db.execute("SELECT * FROM attempts WHERE candidate=?", (candidate_id,)).fetchone()
    if not attempt or attempt["state"] != "accepted_by_gmail":
        raise ValueError("Organization requires confirmed acceptance")
    existing = store.db.execute("SELECT * FROM organization WHERE candidate=?", (candidate_id,)).fetchone()
    if existing and existing["state"] in {"done", "undone"}:
        return existing["state"]
    plan = store.candidate(candidate_id)["plan"]
    if existing:
        changes = json.loads(existing["changes"])
    else:
        thread = mailbox.thread(plan["thread_id"])
        changes = []
        for message in thread:
            if message.id not in plan["captured_ids"] and message.id != attempt["provider_id"]:
                continue
            changes.append({"id": message.id, "add": [] if LABEL in message.labels else [LABEL],
                            "remove": ["INBOX"] if plan["archive"] and message.id in plan["captured_ids"] and "INBOX" in message.labels else []})
        store.db.execute("INSERT INTO organization VALUES(?,?,'pending')", (candidate_id, canonical(changes)))
    try:
        # Only the captured message IDs are mutated, never the thread wholesale.
        for change in changes:
            mailbox.modify(change["id"], change["add"], change["remove"])
    except Exception:
        return "pending"
    store.db.execute("UPDATE organization SET state='done' WHERE candidate=?", (candidate_id,))
    return "done"


def undo(workflow, run_id):
    store, mailbox = workflow.store, workflow.mailbox
    result = []
    rows = store.db.execute("SELECT o.* FROM organization o JOIN candidates c ON c.id=o.candidate WHERE c.run_id=? AND o.state IN ('done','undo_pending')", (run_id,)).fetchall()
    for row in rows:
        store.db.execute("UPDATE organization SET state='undo_pending' WHERE candidate=?", (row["candidate"],))
        try:
            for change in json.loads(row["changes"]):
                mailbox.modify(change["id"], change["remove"], change["add"])
        except Exception:
            continue
        store.db.execute("UPDATE organization SET state='undone' WHERE candidate=?", (row["candidate"],))
        result.append(row["candidate"])
    return result
