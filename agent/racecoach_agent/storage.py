import json
import sqlite3
import threading
import uuid
from pathlib import Path


class AgentStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.c = sqlite3.connect(path, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.c.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY,state TEXT NOT NULL,result TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT,route TEXT NOT NULL,body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        """)

    def queue(self, route, body):
        with self.lock, self.c:
            self.c.execute("INSERT INTO outbox(route,body) VALUES (?,?)", (route, json.dumps(body, allow_nan=False)))

    def pending(self):
        with self.lock:
            row = self.c.execute("SELECT * FROM outbox ORDER BY id LIMIT 1").fetchone()
            return dict(row) if row else None

    def delivered(self, row_id):
        with self.lock, self.c:
            self.c.execute("DELETE FROM outbox WHERE id=?", (row_id,))

    def command(self, command_id):
        with self.lock:
            row = self.c.execute("SELECT * FROM commands WHERE id=?", (command_id,)).fetchone()
            return dict(row) if row else None

    def result(self, command_id, status, result):
        with self.lock, self.c:
            self.c.execute("INSERT OR REPLACE INTO commands VALUES (?,?,?)", (command_id, status, json.dumps(result)))
            self.c.execute("INSERT INTO outbox(route,body) VALUES (?,?)", (f"/api/agent/commands/{command_id}/result", json.dumps({"status": status, "result": result})))

    def get(self, key):
        with self.lock:
            row = self.c.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def set(self, key, value):
        with self.lock, self.c:
            self.c.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, json.dumps(value)))

    def recover_commands(self):
        with self.lock:
            records = self.c.execute("SELECT id FROM commands WHERE state='running'").fetchall()
        for record in records:
            self.result(record[0], "unknown", {"error": "Agent został uruchomiony ponownie; operacja nie jest powtarzana automatycznie"})

    def size(self):
        with self.lock:
            return self.c.execute("SELECT COALESCE(SUM(LENGTH(body)),0) FROM outbox").fetchone()[0]

    def close(self):
        self.c.close()
