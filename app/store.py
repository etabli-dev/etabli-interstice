# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
import json
import sqlite3
import uuid
import threading
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from .domain import Task, graph_order, schedule


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
              CREATE TABLE IF NOT EXISTS operations(client TEXT, key TEXT, request TEXT, result TEXT, PRIMARY KEY(client,key));
              CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, events TEXT, synced TEXT, error TEXT);
              CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at TEXT, action TEXT, object_id TEXT);
            ''')

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
        return [dict(json.loads(r["body"]), id=r["id"], revision=r["revision"],
                     progress=db.execute("SELECT COALESCE(SUM(minutes),0) FROM receipts WHERE task=?", (r["id"],)).fetchone()[0])
                for r in db.execute("SELECT * FROM tasks ORDER BY id")]

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

    def plan(self, now=None):
        with self.db() as db:
            sources = list(db.execute("SELECT * FROM sources"))
            events = [e for row in sources for e in json.loads(row["events"])]
            result = schedule(self._tasks(db), events, self.zone, now=now)
            result["events"] = events
            result["sources"] = [{"id": r["id"], "synced": r["synced"], "error": r["error"]} for r in sources]
            result["mode"] = "test"
            result["calendar_writes"] = False
            return result

    def backup(self, target):
        with self.lock, sqlite3.connect(self.path) as source, sqlite3.connect(target) as destination:
            source.backup(destination)
