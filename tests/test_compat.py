# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from app.compat import Compat
from app.domain import Task
from app.migration import map_task
from app.store import Store, Conflict


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "state.db")
        self.profile = {"id": "hours", "recurringHours": {"monday": [{"startTime": "09:00", "endTime": "17:00"}]}}
        self.raw = {"id": "123", "itemType": "task", "title": "Synthetic task", "notes": "<p>Source marker ABC</p>", "listId": "old-research", "durationMinutes": 60, "minLengthMinutes": 15, "isAutoScheduled": True, "completed": False, "progressMinutes": 20, "schedulingHoursId": "hours", "timeZone": "Europe/Berlin", "customColor": "#112233", "dateCreated": "2026-01-01T00:00:00Z", "lastModified": "2026-01-02T00:00:00Z", "recurrenceRule": None, "blocksIds": [], "blockedByIds": []}
        snapshot = {"list_lists": {"defaultListId": "old-research", "lists": [{"id": "old-research", "title": "Old research", "schedulingHoursId": "hours"}, {"id": "old-study", "title": "Old study", "schedulingHoursId": "hours"}]}, "list_calendars": {"defaultCalendarId": "local", "calendars": [{"id": "local", "title": "Local"}]}, "list_scheduling_hours": {"defaultSchedulingHoursId": "hours", "schedulingHours": [self.profile]}}
        task = map_task(self.raw, {"old-research": {"title": "Research"}}, {"hours": self.profile}, "hours", "Europe/Berlin")
        task.update(category="research", person="Existing Person", tags=["Atlas"])
        with self.store.db() as db:
            db.execute("CREATE TABLE migration_snapshot(sha256 TEXT PRIMARY KEY,body BLOB)")
            db.execute("CREATE TABLE migration_items(source_id TEXT PRIMARY KEY,target_id TEXT,kind TEXT,body TEXT)")
            db.execute("INSERT INTO migration_snapshot VALUES('fixture',?)", (json.dumps(snapshot),))
            for ident, old_list in (("123", "old-research"), ("124", "old-study")):
                raw = dict(self.raw, id=ident, listId=old_list)
                db.execute("INSERT INTO migration_items VALUES(?,?,?,?)", (ident, "flowsavvy:" + ident, "task", json.dumps(raw)))
                db.execute("INSERT INTO tasks VALUES(?,?,1)", ("flowsavvy:" + ident, json.dumps(task)))
            db.execute("INSERT INTO receipts VALUES('migration','123','flowsavvy:123',20)")
        self.compat = Compat(self.store)

    def call(self, name, args=None, key=None):
        return self.compat.call(name, args or {}, "test", key)

    def test_raw_ids_aliases_and_source_fields(self):
        item = self.call("get_item", {"id": "flowsavvy:123"})
        self.assertEqual(item["id"], "123")
        self.assertEqual(item["customColor"], "#112233")
        self.assertEqual(item["progressMinutes"], 20)
        self.assertEqual(self.call("get_list", {"id": "old-study"})["title"], "Research")
        self.assertEqual(len(self.call("list_lists")["lists"]), 2)  # Research and Inbox
        self.assertEqual(len(self.call("list_items", {"itemType": "task", "listId": "old-study"})["items"]), 2)
        with self.assertRaises(KeyError):
            self.call("get_item", {"id": "missing"})

    def test_pagination_query_dates_and_filter_binding(self):
        first = self.call("list_items", {"query": "marker abc", "limit": 1, "completed": "false"})
        self.assertEqual(first["items"][0]["id"], "123")
        second = self.call("list_items", {"query": "marker abc", "limit": 1, "completed": "false", "pageToken": first["nextPageToken"]})
        self.assertEqual(second["items"][0]["id"], "124")
        self.assertIsNone(second["nextPageToken"])
        with self.assertRaises(ValueError):
            self.call("list_items", {"query": "other", "pageToken": first["nextPageToken"]})
        self.assertEqual(self.call("list_items", {"modifiedAfter": "2026-01-02T00:00:00Z"})["items"], [])
        self.call("complete_task", {"id": "123"}, "complete")
        self.assertEqual(len(self.call("list_items", {"completed": True, "modifiedAfter": "2026-01-02T00:00:00Z"})["items"]), 1)

    def test_atomic_update_progress_metadata_and_retry(self):
        item = self.call("get_item", {"id": "123"})
        item.update(title="Changed", progressMinutes=35)
        result = self.call("update_task", item, "edit")
        self.assertEqual(result["category"], "research")
        self.assertEqual(result["person"], "Existing Person")
        self.assertEqual(result["tags"], ["Atlas"])
        self.assertEqual(result["progressMinutes"], 35)
        self.assertEqual(result, self.call("update_task", item, "edit"))
        self.assertEqual(self.store.tasks()[0]["progress"], 35)
        with self.assertRaises(Conflict):
            self.call("update_task", dict(item, title="Different"), "edit")
        with self.assertRaises(Conflict):
            self.call("update_task", dict(item, progressMinutes=34), "bad")
        self.assertEqual(self.call("get_item", {"id": "123"})["title"], "Changed")
        with self.store.db() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM operations WHERE key='bad'").fetchone())

    def test_complete_uncomplete_preserves_progress(self):
        self.assertTrue(self.call("complete_task", {"id": "123"}, "done")["completed"])
        self.assertFalse(self.call("uncomplete_task", {"id": "123"}, "open")["completed"])
        self.assertEqual(self.call("get_item", {"id": "123"})["progressMinutes"], 20)

    def test_create_hook_and_explicit_metadata(self):
        seen = []
        def hook(raw):
            seen.append(dict(raw))
            return {"category": "discussion", "person": "Inferred", **raw}
        self.store._classify_create = hook
        item = self.call("create_task", {"title": "Ask", "listId": "old-study"}, "create")
        self.assertEqual(item["category"], "discussion")
        self.assertEqual(item["person"], "Inferred")
        self.assertNotIn("category", seen[0])
        explicit = self.call("create_task", {"title": "Ask", "category": "other", "person": ""}, "explicit")
        self.assertEqual(explicit["category"], "other")
        self.assertEqual(explicit["person"], "")
        self.assertEqual(item, self.call("create_task", {"title": "Ask", "listId": "old-study"}, "create"))

    def test_events_are_local_transactional_and_busy_correct(self):
        payload = {"title": "Synthetic deadline", "allDay": True, "busy": False, "startDateTime": "2026-12-01T00:00:00", "endDateTime": "2026-12-02T00:00:00"}
        created = self.call("create_event", payload, "event")
        self.assertEqual(created, self.call("create_event", payload, "event"))
        self.assertEqual(len(self.compat.events()), 1)
        self.assertFalse(self.compat.events()[0]["busy"])
        updated = self.call("update_event", dict(created, title="Changed"), "event-edit")
        self.assertEqual(updated["id"], created["id"])
        self.assertEqual(self.call("get_item", {"id": created["id"]})["title"], "Changed")
        with self.assertRaises(ValueError):
            self.call("create_event", dict(payload, endDateTime=payload["startDateTime"]), "bad-event")
        self.assertEqual(len(self.compat.events()), 1)

    def test_unsupported_fields_recurrence_and_dependency_changes_fail_closed(self):
        for payload in ({"surprise": True}, {"recurrenceRule": "FREQ=DAILY"}, {"blocksIds": ["124"]}, {"bufferBeforeMinutes": 10, "bufferAfterMinutes": 20}):
            with self.assertRaises(ValueError):
                self.call("create_task", dict(title="Unsupported", **payload), "bad" + str(payload))
        with self.assertRaises(ValueError):
            self.call("get_item", {"id": "123", "occurrenceDate": "2026-12-01"})
        self.assertEqual(len(self.store.tasks()), 2)

    def test_concurrent_retry_is_one_write(self):
        def create(_):
            return self.call("create_task", {"title": "Concurrent"}, "concurrent")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.store.tasks()), 3)

    def test_native_uuid_tasks_are_visible(self):
        native = self.store.mutate("native", "create", "create", {"title": "Native", "list": "Research"})
        item = self.call("get_item", {"id": native["id"]})
        self.assertEqual(item["id"], native["id"])
        self.assertEqual(item["title"], "Native")

    def test_series_metadata_preserves_occurrence_progress(self):
        template = Task(title="Repeating", list="Research").model_dump(mode="json")
        raw = dict(self.raw, id="series", recurrenceRule="FREQ=DAILY", progressMinutes=0)
        with self.store.db() as db:
            db.execute("INSERT INTO series VALUES(?,?)", ("flowsavvy:series", json.dumps({"id": "flowsavvy:series", "template": template, "rule": "FREQ=DAILY", "anchor": "2026-12-01T10:00:00+01:00", "zone": "Europe/Berlin", "cancelled": []})))
            db.execute("INSERT INTO migration_items VALUES(?,?,?,?)", ("series", "flowsavvy:series", "task", json.dumps(raw)))
            db.execute("INSERT INTO tasks VALUES('occurrence',?,1)", (json.dumps(template),))
            db.execute("INSERT INTO occurrences VALUES('flowsavvy:series','2026-12-01','occurrence')")
            db.execute("INSERT INTO receipts VALUES('focus','timer','occurrence',7)")
        result = self.call("update_task", dict(raw, title="Updated series", notes="New notes"), "series-edit")
        self.assertEqual(result["recurrenceRule"], "FREQ=DAILY")
        with self.store.db() as db:
            occurrence = next(t for t in self.store._tasks(db) if t["id"] == "occurrence")
            self.assertEqual(occurrence["title"], "Updated series")
            self.assertEqual(occurrence["progress"], 7)
        listed = self.call("list_items", {"itemType": "task"})["items"]
        self.assertEqual({item["id"] for item in listed}, {"123", "124", "series"})
        self.assertEqual(next(item for item in listed if item["id"] == "series")["title"], "Updated series")
        with self.assertRaises(ValueError):
            self.call("get_item", {"id": "occurrence"})
        with self.assertRaises(ValueError):
            self.call("update_task", dict(result, durationMinutes=75), "structural")

    def test_old_schema_metadata_and_stale_update(self):
        with self.store.db() as db:
            row = db.execute("SELECT body FROM tasks WHERE id='flowsavvy:123'").fetchone()
            task = json.loads(row[0])
            for key in ("category", "person", "communication_mode", "tags"):
                task.pop(key)
            db.execute("UPDATE tasks SET body=? WHERE id='flowsavvy:123'", (json.dumps(task),))
        before = self.call("get_item", {"id": "123"})
        self.assertEqual(before["category"], "other")
        updated = self.call("update_task", dict(before, title="Current"), "fresh")
        with self.assertRaises(Conflict):
            self.call("update_task", dict(before, title="Stale"), "stale")
        self.assertEqual(updated["title"], "Current")

    def test_partial_updates_preserve_state_and_explicit_null_clears(self):
        before = self.call("get_item", {"id": "123"})
        changed = self.call("update_task", {"id": "123", "notes": "New note"}, "partial")
        for field in ("title", "listId", "durationMinutes", "progressMinutes", "dueDateTime", "category", "person", "tags"):
            self.assertEqual(changed[field], before[field])
        cleared = self.call("update_task", {"id": "123", "notes": None, "dueDateTime": None}, "clear")
        self.assertEqual(cleared["notes"], "")
        self.assertIsNone(cleared["dueDateTime"])
        event = self.call("create_event", {"title": "Event", "allDay": True, "busy": False, "startDateTime": "2026-12-01T00:00:00", "endDateTime": "2026-12-02T00:00:00"}, "event-partial")
        updated = self.call("update_event", {"id": event["id"], "title": "Changed"}, "event-preserve")
        self.assertEqual(updated["startDateTime"], event["startDateTime"])
        self.assertTrue(updated["allDay"])
        self.assertFalse(updated["busy"])

    def test_archived_native_events_and_external_write_scope(self):
        with self.store.db() as db:
            snap = json.loads(db.execute("SELECT body FROM migration_snapshot").fetchone()[0])
            snap["list_calendars"]["calendars"][0]["source"] = "flowsavvy"
            snap["list_calendars"]["calendars"].append({"id": "external", "title": "External", "source": "icloud"})
            db.execute("UPDATE migration_snapshot SET body=?", (json.dumps(snap),))
            for ident, cal in (("native-event", "local"), ("external-event", "external")):
                raw = {"id": ident, "itemType": "event", "calendarId": cal, "title": "Synthetic event", "startDateTime": "2026-12-01T09:00:00", "endDateTime": "2026-12-01T10:00:00", "busy": True}
                db.execute("INSERT INTO migration_items VALUES(?,NULL,'event',?)", (ident, json.dumps(raw)))
        self.assertEqual([e["id"] for e in self.compat.events()], ["native-event"])
        with self.assertRaises(ValueError):
            self.call("update_event", {"id": "external-event", "startDateTime": "2026-12-01T09:00:00", "endDateTime": "2026-12-01T11:00:00"}, "external")
        with self.assertRaises(ValueError):
            self.call("create_event", {"calendarId": "external", "startDateTime": "2026-12-01T09:00:00", "endDateTime": "2026-12-01T11:00:00"}, "external-create")
