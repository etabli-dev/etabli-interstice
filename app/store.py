# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
import json
import hashlib
import sqlite3
import uuid
import threading
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone, timedelta
from .domain import Task, graph_order
from .work import run_job, WorkLimit


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path, zone="Europe/Berlin"):
        self.path, self.zone = str(path), zone
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.db() as db:
            db.executescript('''
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, body TEXT NOT NULL, revision INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS receipts(client TEXT, session TEXT, task TEXT, minutes INTEGER, PRIMARY KEY(client,session));
              CREATE INDEX IF NOT EXISTS receipts_task ON receipts(task);
              CREATE TABLE IF NOT EXISTS operations(client TEXT, key TEXT, request TEXT, result TEXT, PRIMARY KEY(client,key));
              CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, events TEXT, synced TEXT, error TEXT);
              CREATE TABLE IF NOT EXISTS plans(key TEXT PRIMARY KEY, body TEXT NOT NULL, expires TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at TEXT, action TEXT, object_id TEXT);
            ''')
        Path(self.path).chmod(0o600)

    @contextmanager
    def db(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

    def _tasks(self, db):
        return [dict(json.loads(r["body"]), id=r["id"], revision=r["revision"], progress=r["progress"])
                for r in db.execute("""SELECT tasks.*, COALESCE(p.minutes, 0) AS progress FROM tasks
                    LEFT JOIN (SELECT task, SUM(minutes) AS minutes FROM receipts GROUP BY task) p
                    ON tasks.id=p.task ORDER BY tasks.id""")]

    def tasks(self):
        with self.db() as db:
            return self._tasks(db)

    def operation(self, client, key):
        with self.db() as db:
            row = db.execute("SELECT result FROM operations WHERE client=? AND key=?", (client, key)).fetchone()
            if not row:
                raise KeyError(key)
            return json.loads(row[0])

    def mutate(self, client, key, action, payload, ident=None, revision=None):
        if not key or len(key) > 200:
            raise ValueError("A bounded Idempotency-Key is required")
        signature = json.dumps([action, ident, revision, payload], sort_keys=True)
        with self.db() as db:
            previous = db.execute("SELECT request,result FROM operations WHERE client=? AND key=?", (client, key)).fetchone()
            if previous:
                if previous["request"] != signature:
                    raise Conflict("Idempotency key was already used for different input")
                return json.loads(previous["result"])
            tasks = self._tasks(db)
            current = next((t for t in tasks if t["id"] == ident), None)
            if action != "create" and not current:
                raise KeyError(ident)
            if action in ("update", "complete") and current["revision"] != revision:
                raise Conflict("Task changed; refresh before editing")
            if action in ("create", "update", "complete"):
                raw = {k: v for k, v in (current or {}).items() if k in Task.model_fields}
                raw.update(payload)
                if action == "complete":
                    raw["completed"] = True
                task = Task.model_validate(raw).model_dump(mode="json")
                if task["fixed_start"] and task["dependencies"]:
                    raise ValueError("Pinned dependencies are not supported in the test planner")
                ident = ident or str(uuid.uuid4())
                task["id"] = ident
                graph_order([t for t in tasks if t["id"] != ident] + [task])
                task.pop("id")
                version = current["revision"] + 1 if current else 1
                if not current and len(tasks) >= 1000:
                    raise ValueError("Test instance task limit reached")
                db.execute("INSERT INTO tasks VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,revision=excluded.revision", (ident, json.dumps(task), version))
            elif action == "progress":
                session, minutes = payload["session_id"], payload["minutes"]
                if not isinstance(session, str) or not 1 <= len(session) <= 150 or type(minutes) is not int or not 0 <= minutes <= 10080:
                    raise ValueError("Invalid cumulative session progress")
                row = db.execute("SELECT * FROM receipts WHERE client=? AND session=?", (client, session)).fetchone()
                if row and row["task"] != ident:
                    raise Conflict("Session already belongs to another task")
                if row and minutes < row["minutes"]:
                    raise Conflict("Cumulative progress cannot decrease")
                if not row or minutes != row["minutes"]:
                    db.execute("INSERT INTO receipts VALUES(?,?,?,?) ON CONFLICT(client,session) DO UPDATE SET minutes=excluded.minutes", (client, session, ident, minutes))
                    db.execute("UPDATE tasks SET revision=revision+1 WHERE id=?", (ident,))
            else:
                raise ValueError("Unknown operation")
            result = next(t for t in self._tasks(db) if t["id"] == ident)
            db.execute("INSERT INTO operations VALUES(?,?,?,?)", (client, key, signature, json.dumps(result)))
            db.execute("INSERT INTO audit(at,action,object_id) VALUES(?,?,?)", (datetime.now(timezone.utc).isoformat(), action, ident))
            return result

    def source_result(self, ident, events=None, error=None):
        with self.db() as db:
            if error:
                db.execute("INSERT INTO sources VALUES(?,'[]',NULL,?) ON CONFLICT(id) DO UPDATE SET error=excluded.error", (ident, error))
            else:
                db.execute("INSERT INTO sources VALUES(?,?,?,NULL) ON CONFLICT(id) DO UPDATE SET events=excluded.events,synced=excluded.synced,error=NULL", (ident, json.dumps(events), datetime.now(timezone.utc).isoformat()))

    def _snapshot(self, db):
        sources = [dict(row) for row in db.execute("SELECT * FROM sources ORDER BY id")]
        tasks = self._tasks(db)
        digest = hashlib.sha256(json.dumps([tasks, sources, self.zone], sort_keys=True).encode()).hexdigest()
        return tasks, sources, digest

    def plan(self, now=None):
        now = now or datetime.now(timezone.utc)
        with self.db() as db:
            tasks, sources, digest = self._snapshot(db)
            cached = db.execute("SELECT * FROM plans WHERE key=?", (digest,)).fetchone()
            if cached and now < datetime.fromisoformat(cached["expires"]):
                result = json.loads(cached["body"])
            else:
                result = None
        events = [e for row in sources for e in json.loads(row["events"])]
        if len(events) > 5000:
            raise WorkLimit("Combined calendar event limit exceeded")
        if result is None:
            result = run_job("schedule", {"tasks": tasks, "events": events, "zone": self.zone, "now": now.isoformat()})
            result["inputs_revision"] = digest
            expires = min([now + timedelta(minutes=5)] +
                          [datetime.fromisoformat(b["start"]) for b in result["blocks"]])
            with self.db() as db:
                if self._snapshot(db)[2] != digest:
                    raise Conflict("Planning inputs changed; refresh the plan")
                db.execute("DELETE FROM plans")
                db.execute("INSERT INTO plans VALUES(?,?,?)", (digest, json.dumps(result), expires.isoformat()))
        result["events"] = events
        result["sources"] = [{"id": r["id"], "synced": r["synced"], "error": r["error"],
            "stale": bool(r["error"] or not r["synced"] or
                now - datetime.fromisoformat(r["synced"]) > timedelta(minutes=15))} for r in sources]
        result["calendar_inputs_ready"] = all(not s["stale"] for s in result["sources"])
        result["mode"] = "test"
        result["calendar_writes"] = False
        return result

    def configure_sources(self, identifiers):
        # Remove disconnected calendars and explicitly mark sources awaiting their first refresh.
        with self.db() as db:
            for row in db.execute("SELECT id FROM sources").fetchall():
                if row["id"] not in identifiers:
                    db.execute("DELETE FROM sources WHERE id=?", (row["id"],))
            for ident in identifiers:
                db.execute("INSERT OR IGNORE INTO sources VALUES(?,'[]',NULL,'Awaiting first refresh')", (ident,))

    def backup(self, target):
        with self.lock, sqlite3.connect(self.path) as source, sqlite3.connect(target) as destination:
            source.backup(destination)
