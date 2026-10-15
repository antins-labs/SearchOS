from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS schedules (
 id TEXT PRIMARY KEY, version INTEGER NOT NULL, payload TEXT NOT NULL,
 active INTEGER NOT NULL, next_run REAL, created REAL NOT NULL, updated REAL NOT NULL,
 deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, schedule_id TEXT, slot TEXT, session_id TEXT,
 status TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL,
 updated REAL NOT NULL, error TEXT NOT NULL DEFAULT '', report_id TEXT,
 UNIQUE(schedule_id, slot)
);
CREATE TABLE IF NOT EXISTS reports (
 id TEXT PRIMARY KEY, run_id TEXT UNIQUE NOT NULL, session_id TEXT NOT NULL,
 payload TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
 id TEXT PRIMARY KEY, run_id TEXT UNIQUE, kind TEXT NOT NULL, title TEXT NOT NULL,
 body TEXT NOT NULL, url TEXT NOT NULL, created REAL NOT NULL, read_at REAL
);
CREATE TABLE IF NOT EXISTS devices (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL,
 admin INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, last_seen REAL NOT NULL,
 expires REAL NOT NULL, revoked REAL
);
CREATE TABLE IF NOT EXISTS pairings (
 id TEXT PRIMARY KEY, code_hash TEXT UNIQUE NOT NULL, expires REAL NOT NULL,
 consumed REAL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (bucket TEXT PRIMARY KEY, started REAL, count INTEGER);
CREATE TABLE IF NOT EXISTS subscriptions (
 id TEXT PRIMARY KEY, device_id TEXT NOT NULL, endpoint_hash TEXT UNIQUE NOT NULL,
 payload TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS preferences (device_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox (
 id TEXT PRIMARY KEY, notification_id TEXT NOT NULL, subscription_id TEXT NOT NULL,
 status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_try REAL NOT NULL,
 error TEXT NOT NULL DEFAULT '', UNIQUE(notification_id, subscription_id)
);
CREATE INDEX IF NOT EXISTS runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS outbox_due ON outbox(status, next_try);
"""


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "assistant.sqlite3"
        with self.connect() as db:
            db.executescript(SCHEMA)
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=10000")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    def rows(self, sql, args=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def execute(self, sql, args=()):
        with self.connect() as db:
            return db.execute(sql, args).rowcount

    def rate_limit(self, bucket: str, now: float, limit=10, window=300) -> bool:
        with self.transaction() as db:
            db.execute("DELETE FROM attempts WHERE bucket=? AND started < ?", (bucket, now - window))
            row = db.execute("SELECT count FROM attempts WHERE bucket=?", (bucket,)).fetchone()
            if row and row[0] >= limit:
                return False
            db.execute("INSERT INTO attempts VALUES(?,?,1) ON CONFLICT(bucket) DO UPDATE SET count=count+1", (bucket, now))
            return True
