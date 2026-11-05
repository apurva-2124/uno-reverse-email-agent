"""Validated data at the boundaries; message content is never instructions."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email import policy
from email.parser import HeaderParser
from hashlib import sha256
import json
import re
from urllib.parse import urlparse


def now() -> float:
    return datetime.now(timezone.utc).timestamp()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value) -> str:
    return sha256(canonical(value).encode()).hexdigest()


def address(value: str) -> str:
    if not isinstance(value, str) or any(c in value for c in "\r\n\x00"):
        raise ValueError("Invalid address header")
    header = HeaderParser(policy=policy.default).parsestr(f"To: {value}\n\n")["To"]
    if header.defects or len(header.addresses) != 1:
        raise ValueError("Exactly one valid recipient is required")
    addr = header.addresses[0]
    if not addr.username or not addr.domain or "." not in addr.domain:
        raise ValueError("A complete email address is required")
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", addr.username):
        raise ValueError("Unsupported email local part")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", addr.domain):
        raise ValueError("Unsupported email domain")
    return addr.addr_spec.lower()


@dataclass(frozen=True)
class Profile:
    business: str
    domain: str
    description: str
    cta: str
    signature: str

    def __post_init__(self):
        for value in asdict(self).values():
            if not isinstance(value, str) or not value.strip() or len(value) > 2000:
                raise ValueError("Profile fields must be nonempty strings up to 2000 characters")
        if "\n" in self.business or "\r" in self.business:
            raise ValueError("Business name must be a single line")
        if not re.fullmatch(r"[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", self.domain):
            raise ValueError("Use a canonical business domain")
        parsed = urlparse(self.cta)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("CTA must be an HTTPS URL without credentials")

    @property
    def version(self):
        return digest(asdict(self))


@dataclass
class Message:
    id: str
    thread_id: str
    sender: str
    subject: str
    body: str
    received_at: float
    message_id: str
    reply_to: str = ""
    references: str = ""
    labels: list[str] = field(default_factory=lambda: ["INBOX"])
    headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if len(self.body) > 100_000 or len(self.subject) > 1000:
            raise ValueError("Message exceeds processing limits")
        if any(c in self.subject for c in "\r\n\x00"):
            raise ValueError("Invalid subject")

    @property
    def fingerprint(self):
        data = asdict(self)
        data.pop("labels")
        return digest(data)

    @property
    def recipient(self):
        return address(self.reply_to or self.sender)


@dataclass(frozen=True)
class Decision:
    category: str
    reason: str
    brand: str = ""
    company: str = ""
    evidence: str = ""
    automatic: bool = False
