"""Conservative, synthetic-only classifier. Never a live-mail release gate."""
import re
from .models import Decision, Message, address

VERSION = "synthetic-rules-v1"
PROTECTED = re.compile(
    r"password|verification|verify your|security|invoice|receipt|payment|"
    r"application|interview|resume|support ticket|help desk|press inquiry|"
    r"unsubscribe|newsletter|out of office|automated|do not reply", re.I
)
SALES = re.compile(r"(?:book|schedule) (?:a |an )?(?:demo|call)|interested in (?:a |our )?demo", re.I)


def classify(message: Message, thread: list[Message], mailbox: str,
             brands: dict[str, dict]) -> Decision:
    """Brands are user-supplied sender-domain mappings, never inferred from TLDs."""
    if set(message.labels) & {"SENT", "DRAFT", "SPAM", "TRASH"}:
        return Decision("excluded", "Excluded mailbox label")
    try:
        sender, recipient = address(message.sender), message.recipient
    except ValueError:
        return Decision("excluded", "Malformed or multiple recipient addresses")
    if sender == mailbox or recipient == mailbox:
        return Decision("excluded", "Self-sent message")
    local = recipient.split("@")[0]
    if re.search(r"no[._-]?reply|do[._-]?not[._-]?reply|mailer-daemon|postmaster", local):
        return Decision("excluded", "Unmonitored or automated recipient")
    headers = {k.lower(): v for k, v in message.headers.items()}
    if (headers.get("auto-submitted", "no").lower() != "no"
            or headers.get("list-id") or headers.get("precedence", "").lower() in {"bulk", "list", "junk"}):
        return Decision("excluded", "Automated or mailing-list message")
    text = message.subject + "\n" + message.body
    if PROTECTED.search(text):
        return Decision("excluded", "Protected or opted-out category")
    if any("SENT" in item.labels for item in thread):
        return Decision("needs_review", "Existing two-way conversation")
    if sender.split("@")[1] != recipient.split("@")[1]:
        return Decision("needs_review", "Reply-To identity differs from sender")
    brand = brands.get(sender.split("@")[1])
    if not brand or not brand.get("id") or not brand.get("name"):
        return Decision("needs_review", "Company identity requires confirmation")
    # Require the configured company in the message as additional evidence.
    if not re.search(r"\b" + re.escape(brand["name"]) + r"\b", message.body, re.I):
        return Decision("needs_review", "Configured company is not supported by message context")
    match = SALES.search(text)
    if not match:
        return Decision("needs_review", "No unambiguous sales evidence")
    return Decision("sales", "Demo sales phrase and configured company match",
                    brand["id"], brand["name"], match.group(0), True)


def evaluate() -> dict:
    """Small demonstrator gate; explicitly insufficient for live deployment."""
    cases = [
        ("Want to book a demo? — Acme", {}, "sales"),
        ("Reset your password. Book a demo — Acme", {}, "excluded"),
        ("Your invoice is ready. Book a demo — Acme", {}, "excluded"),
        ("Job application: book a demo — Acme", {}, "excluded"),
        ("Support ticket: book a demo — Acme", {}, "excluded"),
        ("Weekly newsletter: book a demo — Acme", {}, "excluded"),
        ("Book a demo — Acme", {"Auto-Submitted": "auto-replied"}, "excluded"),
        ("How was your weekend? — Acme", {}, "needs_review"),
        ("Book a demo — Someone Else", {}, "needs_review"),
    ]
    failures = []
    for i, (body, headers, expected) in enumerate(cases):
        m = Message(str(i), str(i), "seller@acme.example", "Hello", body, 0, f"<{i}@acme.example>", headers=headers)
        result = classify(m, [m], "owner@demo.example", {"acme.example": {"id": "acme", "name": "Acme"}})
        if result.category != expected:
            failures.append(i)
    return {"version": VERSION, "cases": len(cases), "failures": failures,
            "passed": not failures, "scope": "synthetic-only"}
