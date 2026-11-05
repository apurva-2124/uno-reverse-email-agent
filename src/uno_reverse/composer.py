"""Bounded, profile-backed text and MIME generation."""
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate
import html
import re
from .models import Profile, Message, address

TEMPLATE_VERSION = "warm-v1"
ID = re.compile(r"<[^<>\s@]+@[^<>\s@]+>")


def draft(profile: Profile, company: str) -> str:
    greeting = f"Hi {company} team" if company != "there" else "Hi there"
    return (f"{greeting},\n\nThanks for reaching out — a little reverse pitch in return!\n\n"
            f"{profile.business}: {profile.description}\n\n"
            f"If that sounds useful: {profile.cta}\n\n{profile.signature}")


def reply_subject(subject: str) -> str:
    return "Re: " + re.sub(r"^(?:re:\s*)+", "", subject.strip(), flags=re.I)


def threading(message: Message) -> tuple[str, str]:
    if not ID.fullmatch(message.message_id):
        raise ValueError("Source Message-ID is invalid; review another source message")
    refs = message.references.split()
    if len(refs) > 50 or any(not ID.fullmatch(ref) for ref in refs):
        raise ValueError("Source References header is invalid")
    return message.message_id, " ".join(dict.fromkeys([*refs, message.message_id]))


def mime(plan: dict, sender: str, message_id: str, timestamp: float) -> bytes:
    msg = EmailMessage(policy=SMTP)
    msg["From"] = address(sender)
    msg["To"] = address(plan["recipient"])
    msg["Subject"] = plan["subject"]
    msg["Message-ID"] = message_id
    msg["Date"] = formatdate(timestamp, usegmt=True)
    msg["In-Reply-To"] = plan["in_reply_to"]
    msg["References"] = plan["references"]
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(plan["body"])
    msg.add_alternative("<html><body><p>" + html.escape(plan["body"]).replace("\n", "<br>\n") + "</p></body></html>", subtype="html")
    return msg.as_bytes()
