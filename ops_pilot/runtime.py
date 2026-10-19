"""Private durable monitor controls and bounded alert history, scoped to one app."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time


class Runtime:
    def __init__(self, directory, config):
        directory = Path(directory).expanduser()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / 'monitor.sqlite3'
        self.key = hashlib.sha256(json.dumps([config[k] for k in
            ('docker_context', 'container', 'health_url')]).encode()).hexdigest()
        # Create privately before SQLite opens it (also protects crash journals).
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS controls (target TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY, target TEXT, time REAL, event TEXT, delivery TEXT)')

    def connect(self):
        return sqlite3.connect(self.path)

    def load(self):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM controls WHERE target=?', (self.key,)).fetchone()
        return json.loads(row[0]) if row else {}

    def save(self, enabled, maintenance_until, failed):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO controls VALUES (?,?)',
                       (self.key, json.dumps(dict(enabled=enabled, maintenance_until=maintenance_until, failed=failed))))

    def record(self, event, delivery):
        with self.connect() as db:
            cursor = db.execute('INSERT INTO alerts(target,time,event,delivery) VALUES (?,?,?,?)',
                                (self.key, time.time(), event, delivery))
            db.execute('DELETE FROM alerts WHERE id NOT IN (SELECT id FROM alerts ORDER BY id DESC LIMIT 500)')
            return cursor.lastrowid

    def delivered(self, alert_id, outcome):
        with self.connect() as db:
            db.execute('UPDATE alerts SET delivery=? WHERE id=? AND target=?', (outcome, alert_id, self.key))

    def alerts(self):
        with self.connect() as db:
            return [dict(time=t, event=e, delivery=d) for t,e,d in db.execute(
                'SELECT time,event,delivery FROM alerts WHERE target=? ORDER BY id DESC LIMIT 30', (self.key,))]
