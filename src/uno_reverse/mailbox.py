"""Adapter contract and persistent synthetic mailbox, with deliberate fault injection."""
from __future__ import annotations
import base64
from dataclasses import asdict
from email import policy
from email.parser import BytesParser
import json
import os
from pathlib import Path
from typing import Protocol
from uuid import uuid4
from .models import Message, address, now


class BeforeSubmissionError(Exception):
    """The adapter guarantees no submission took place."""


class MailboxAdapter(Protocol):
    identity: str
    synthetic: bool

    def scan(self, since: float) -> list[Message]: ...
    def thread(self, thread_id: str) -> list[Message]: ...
    def send(self, raw: bytes, thread_id: str) -> str: ...
    def find_sent(self, message_id: str, recipient: str, thread_id: str) -> str | None: ...
    def modify(self, message_id: str, add: list[str], remove: list[str]) -> None: ...


class FakeMailbox:
    synthetic = True

    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.identity = address(self._read()["identity"])
        self.send_fault = None
        self.organization_fault = False

    def _read(self):
        return json.loads(self.path.read_text())

    def _write(self, data):
        temp = self.path.with_name(self.path.name + "." + uuid4().hex + ".tmp")
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as out:
            json.dump(data, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, self.path)

    def messages(self):
        return [Message(**m) for m in self._read()["messages"]]

    def scan(self, since):
        return [m for m in self.messages() if m.received_at >= since and "INBOX" in m.labels]

    def thread(self, thread_id):
        return [m for m in self.messages() if m.thread_id == thread_id]

    def send(self, raw, thread_id):
        if self.send_fault == "before":
            raise BeforeSubmissionError("Synthetic pre-submission failure")
        if self.send_fault == "unknown":
            raise TimeoutError("Synthetic ambiguous request")
        msg = BytesParser(policy=policy.default).parsebytes(raw)
        data = self._read()
        provider_id = uuid4().hex
        body = msg.get_body(preferencelist=("plain",)).get_content()
        sent = Message(provider_id, thread_id, str(msg["From"]), str(msg["Subject"]), body,
                       now(), str(msg["Message-ID"]), labels=["SENT"], headers={"To": str(msg["To"])})
        data["messages"].append(asdict(sent))
        data.setdefault("submitted", []).append({"id": provider_id, "raw": base64.b64encode(raw).decode()})
        self._write(data)
        if self.send_fault == "accepted_timeout":
            raise TimeoutError("Synthetic timeout after acceptance")
        return provider_id

    def find_sent(self, message_id, recipient, thread_id):
        matches = [m for m in self.messages() if m.message_id == message_id and "SENT" in m.labels
                   and m.thread_id == thread_id and address(m.sender) == self.identity
                   and address(m.headers.get("To", "")) == recipient]
        return matches[0].id if len(matches) == 1 else None

    def modify(self, message_id, add, remove):
        if self.organization_fault:
            raise OSError("Synthetic label failure")
        data = self._read()
        for message in data["messages"]:
            if message["id"] == message_id:
                message["labels"] = sorted((set(message["labels"]) | set(add)) - set(remove))
                self._write(data)
                return
        raise ValueError("Message not found")

    def append(self, message):
        data = self._read()
        data["messages"].append(asdict(message))
        self._write(data)


def create_demo(path):
    mailbox = Path(path)
    if mailbox.exists():
        raise ValueError("Demo mailbox already exists; use another state directory")
    messages = [
        Message("sales-1", "thread-acme", "Sam <sam@acme.example>", "A quick demo?",
                "Hi! Would you like to book a demo?\nSam, Acme", now() - 60, "<sales-1@acme.example>"),
        Message("security-1", "thread-security", "security@secure.example", "Reset your password",
                "Your security verification code is 123456.", now() - 120, "<security-1@secure.example>"),
        Message("personal-1", "thread-personal", "friend@friend.example", "Lunch?",
                "Want to get lunch tomorrow?", now() - 180, "<personal-1@friend.example>"),
    ]
    fd = os.open(mailbox, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump({"identity": "owner@demo.example", "messages": [asdict(m) for m in messages]}, out)
    return FakeMailbox(mailbox)
