"""Durable state and cross-process transactions. Never stores credentials."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import sqlite3
from .models import canonical

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, created REAL NOT NULL, scope TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candidates(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL, source_id TEXT NOT NULL UNIQUE,
 plan TEXT NOT NULL, state TEXT NOT NULL, authorization TEXT, policy_id TEXT);
CREATE TABLE IF NOT EXISTS reservations(brand TEXT PRIMARY KEY, candidate TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS attempts(
 candidate TEXT PRIMARY KEY, message_id TEXT UNIQUE NOT NULL, mime BLOB NOT NULL,
 state TEXT NOT NULL, submitted REAL NOT NULL, day TEXT NOT NULL, provider_id TEXT,
 authorization TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS suppressions(target TEXT PRIMARY KEY, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS policies(id TEXT PRIMARY KEY, value TEXT NOT NULL, active INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS organization(
 candidate TEXT PRIMARY KEY, changes TEXT NOT NULL, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS replies(
 message_id TEXT PRIMARY KEY, candidate TEXT NOT NULL, category TEXT NOT NULL,
 received REAL NOT NULL, evidence TEXT NOT NULL);
"""


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        path = self.directory / "state.sqlite3"
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(path, 0o600)
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    @contextmanager
    def sender_lock(self):
        # A crash releases this OS lock. Recover submitting attempts only while held.
        fd = os.open(self.directory / "sender.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise ValueError("Another worker is submitting; try again later") from None
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        self.db.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, canonical(value)))

    def candidate(self, candidate_id):
        row = self.db.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone()
        if row is None:
            raise ValueError("Candidate does not exist")
        result = dict(row)
        result["plan"] = json.loads(result["plan"])
        return result

    def candidates(self, run_id=None):
        rows = self.db.execute("SELECT id FROM candidates" + (" WHERE run_id=?" if run_id else "") + " ORDER BY rowid",
                               (run_id,) if run_id else ())
        return [self.candidate(row[0]) for row in rows.fetchall()]

    def export(self):
        tables = ("settings", "runs", "candidates", "reservations", "suppressions", "policies", "organization", "replies")
        result = {name: [dict(row) for row in self.db.execute(f"SELECT * FROM {name}")] for name in tables}
        result["attempts"] = [dict(row) for row in self.db.execute(
            "SELECT candidate,message_id,state,submitted,day,provider_id,authorization FROM attempts")]
        return result
