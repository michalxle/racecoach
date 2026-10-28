from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def uid() -> str:
    return uuid.uuid4().hex


def dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('instructor','trainee','service')), password_hash TEXT NOT NULL,
 created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS trainees (
 user_id TEXT PRIMARY KEY REFERENCES users(id), notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS tracks (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, layout TEXT NOT NULL, length REAL NOT NULL,
 geometry TEXT NOT NULL, sections TEXT NOT NULL, version TEXT NOT NULL, source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exercises (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, track_id TEXT NOT NULL REFERENCES tracks(id),
 car TEXT NOT NULL, conditions TEXT NOT NULL, duration INTEGER NOT NULL, mode TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS plans (
 id TEXT PRIMARY KEY, trainee_id TEXT NOT NULL REFERENCES trainees(user_id), title TEXT NOT NULL,
 created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS plan_items (
 id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES plans(id), exercise_id TEXT NOT NULL REFERENCES exercises(id),
 title TEXT NOT NULL, goal TEXT NOT NULL, criteria TEXT NOT NULL, mode TEXT NOT NULL,
 sequence INTEGER NOT NULL, scheduled TEXT, status TEXT NOT NULL DEFAULT 'planned', revision INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS stations (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, simulated INTEGER NOT NULL,
 created REAL NOT NULL, last_seen REAL, state TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, mode TEXT NOT NULL, exercise_id TEXT NOT NULL REFERENCES exercises(id),
 scenario TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, ended REAL
);
CREATE TABLE IF NOT EXISTS attempts (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), trainee_id TEXT NOT NULL REFERENCES trainees(user_id),
 station_id TEXT NOT NULL REFERENCES stations(id), plan_item_id TEXT REFERENCES plan_items(id),
 status TEXT NOT NULL, config TEXT NOT NULL DEFAULT '{}', note TEXT NOT NULL DEFAULT '',
 result TEXT NOT NULL DEFAULT '{}', last_seq INTEGER NOT NULL DEFAULT -1, created REAL NOT NULL,
 UNIQUE(run_id,station_id), UNIQUE(run_id,trainee_id)
);
CREATE TABLE IF NOT EXISTS commands (
 id TEXT PRIMARY KEY, station_id TEXT NOT NULL REFERENCES stations(id), kind TEXT NOT NULL,
 payload TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL,
 result TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS commands_station ON commands(station_id,created);
CREATE TABLE IF NOT EXISTS telemetry_chunks (
 attempt_id TEXT NOT NULL REFERENCES attempts(id), chunk_id TEXT NOT NULL,
 first_seq INTEGER NOT NULL, last_seq INTEGER NOT NULL, count INTEGER NOT NULL,
 checksum TEXT NOT NULL, data BLOB NOT NULL, created REAL NOT NULL,
 PRIMARY KEY(attempt_id,chunk_id)
);
CREATE TABLE IF NOT EXISTS audit (
 id TEXT PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL,
 detail TEXT NOT NULL, created REAL NOT NULL
);
PRAGMA user_version=1;
"""


class Database:
    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.lock = threading.RLock()
        with self.lock:
            self.connection.executescript(SCHEMA)
            if "game_id" not in {row[1] for row in self.connection.execute("PRAGMA table_info(tracks)")}:
                self.connection.execute("ALTER TABLE tracks ADD COLUMN game_id TEXT")
                self.connection.execute("UPDATE tracks SET game_id=id")
                self.connection.execute("PRAGMA user_version=2")
                self.connection.commit()

    @contextmanager
    def transaction(self):
        with self.lock:
            try:
                yield self.connection
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    def one(self, query, args=()):
        with self.lock:
            row = self.connection.execute(query, args).fetchone()
            return dict(row) if row else None

    def all(self, query, args=()):
        with self.lock:
            return [dict(row) for row in self.connection.execute(query, args).fetchall()]

    def audit(self, actor, action, target, detail=None, conn=None):
        values = (uid(), actor, action, target, dump(detail or {}), time.time())
        if conn is not None:
            conn.execute("INSERT INTO audit VALUES (?,?,?,?,?,?)", values)
        else:
            with self.transaction() as c:
                c.execute("INSERT INTO audit VALUES (?,?,?,?,?,?)", values)

    def close(self):
        with self.lock:
            self.connection.close()
