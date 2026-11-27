# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
"""Transactional legacy contract adapter for migrated clients.

No calls or writes to the source provider. Unsupported recurrence mutations and
unrepresentable fields fail closed, without changing tasks or progress receipts.
"""
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import uuid
from zoneinfo import ZoneInfo
from urllib.parse import quote

from .domain import Task, graph_order
from .migration import local_time, map_task
from .store import Conflict

SCHEMAS = {'uncomplete_task': {'type': 'object', 'properties': {'id': {'type': 'string'}}, 'required': ['id']},
 'create_event': {'type': 'object',
                  'properties': {'bufferAfterMinutes': {'type': 'integer', 'format': 'int'},
                                 'bufferBeforeMinutes': {'type': 'integer', 'format': 'int'},
                                 'customColor': {'type': 'string'},
                                 'notes': {'type': 'string'},
                                 'recurrenceRule': {'type': 'string'},
                                 'timeZone': {'type': 'string'},
                                 'title': {'type': 'string'},
                                 'allDay': {'type': 'boolean'},
                                 'busy': {'type': 'boolean'},
                                 'calendarId': {'type': 'string'},
                                 'endDateTime': {'type': 'string', 'format': 'local-date-time'},
                                 'location': {'type': 'string'},
                                 'startDateTime': {'type': 'string', 'format': 'local-date-time'}},
                  'additionalProperties': False,
                  'required': ['endDateTime', 'startDateTime']},
 'get_list': {'type': 'object', 'properties': {'id': {'type': 'string'}}, 'required': ['id']},
 'update_event': {'type': 'object',
                  'properties': {'id': {'type': 'string'},
                                 'occurrenceDate': {'type': 'string', 'format': 'date'},
                                 'scope': {'enum': ['thisOccurrence', 'thisAndFutureOccurrences'],
                                           'type': 'string'},
                                 'bufferAfterMinutes': {'type': 'integer', 'format': 'int'},
                                 'bufferBeforeMinutes': {'type': 'integer', 'format': 'int'},
                                 'customColor': {'type': 'string'},
                                 'notes': {'type': 'string'},
                                 'recurrenceRule': {'type': 'string'},
                                 'timeZone': {'type': 'string'},
                                 'title': {'type': 'string'},
                                 'allDay': {'type': 'boolean'},
                                 'busy': {'type': 'boolean'},
                                 'calendarId': {'type': 'string'},
                                 'endDateTime': {'type': 'string', 'format': 'local-date-time'},
                                 'location': {'type': 'string'},
                                 'startDateTime': {'type': 'string', 'format': 'local-date-time'}},
                  'additionalProperties': False,
                  'required': ['id', 'endDateTime', 'startDateTime']},
 'update_task': {'type': 'object',
                 'properties': {'id': {'type': 'string'},
                                'occurrenceDate': {'type': 'string', 'format': 'date'},
                                'scope': {'enum': ['thisOccurrence', 'thisAndFutureOccurrences'],
                                          'type': 'string'},
                                'bufferAfterMinutes': {'type': 'integer', 'format': 'int'},
                                'bufferBeforeMinutes': {'type': 'integer', 'format': 'int'},
                                'customColor': {'type': 'string'},
                                'notes': {'type': 'string'},
                                'recurrenceRule': {'type': 'string'},
                                'timeZone': {'type': 'string'},
                                'title': {'type': 'string'},
                                'blockedByIds': {'type': 'array', 'items': {'type': 'string'}},
                                'blocksIds': {'type': 'array', 'items': {'type': 'string'}},
                                'canBeStartedAt': {'type': 'string', 'format': 'local-date-time'},
                                'dueDateTime': {'type': 'string', 'format': 'local-date-time'},
                                'durationMinutes': {'type': 'integer', 'format': 'int'},
                                'endDateTime': {'type': 'string', 'format': 'local-date-time'},
                                'isAutoIgnored': {'type': 'boolean'},
                                'isAutoScheduled': {'type': 'boolean'},
                                'listId': {'type': 'string'},
                                'minLengthMinutes': {'type': 'integer', 'format': 'int'},
                                'priority': {'enum': ['low', 'normal', 'high', 'asap'], 'type': 'string'},
                                'progressMinutes': {'type': 'integer', 'format': 'int'},
                                'schedulingHoursId': {'type': 'string'},
                                'startDateTime': {'type': 'string', 'format': 'local-date-time'},
                                'category': {'type': 'string'},
                                'person': {'type': 'string'},
                                'communication_mode': {'type': 'string'},
                                'tags': {'type': 'array', 'items': {'type': 'string'}}},
                 'additionalProperties': False,
                 'required': ['id']},
 'list_items': {'type': 'object',
                'properties': {'modifiedAfter': {'type': 'string', 'format': 'utc-date-time'},
                               'itemType': {'enum': ['task', 'event'], 'type': 'string'},
                               'completed': {'type': 'boolean', 'default': False},
                               'listId': {'type': 'string'},
                               'calendarId': {'type': 'string'},
                               'query': {'type': 'string'},
                               'pageToken': {'type': 'string'},
                               'limit': {'type': 'integer', 'format': 'int', 'default': 50}}},
 'list_lists': {'type': 'object', 'properties': {}},
 'create_task': {'type': 'object',
                 'properties': {'bufferAfterMinutes': {'type': 'integer', 'format': 'int'},
                                'bufferBeforeMinutes': {'type': 'integer', 'format': 'int'},
                                'customColor': {'type': 'string'},
                                'notes': {'type': 'string'},
                                'recurrenceRule': {'type': 'string'},
                                'timeZone': {'type': 'string'},
                                'title': {'type': 'string'},
                                'blockedByIds': {'type': 'array', 'items': {'type': 'string'}},
                                'blocksIds': {'type': 'array', 'items': {'type': 'string'}},
                                'canBeStartedAt': {'type': 'string', 'format': 'local-date-time'},
                                'dueDateTime': {'type': 'string', 'format': 'local-date-time'},
                                'durationMinutes': {'type': 'integer', 'format': 'int'},
                                'endDateTime': {'type': 'string', 'format': 'local-date-time'},
                                'isAutoIgnored': {'type': 'boolean'},
                                'isAutoScheduled': {'type': 'boolean'},
                                'listId': {'type': 'string'},
                                'minLengthMinutes': {'type': 'integer', 'format': 'int'},
                                'priority': {'enum': ['low', 'normal', 'high', 'asap'], 'type': 'string'},
                                'progressMinutes': {'type': 'integer', 'format': 'int'},
                                'schedulingHoursId': {'type': 'string'},
                                'startDateTime': {'type': 'string', 'format': 'local-date-time'},
                                'category': {'type': 'string'},
                                'person': {'type': 'string'},
                                'communication_mode': {'type': 'string'},
                                'tags': {'type': 'array', 'items': {'type': 'string'}}},
                 'additionalProperties': False},
 'complete_task': {'type': 'object',
                   'properties': {'id': {'type': 'string'},
                                  'occurrenceDate': {'type': 'string', 'format': 'date'}},
                   'required': ['id']},
 'list_calendars': {'type': 'object', 'properties': {}},
 'get_item': {'type': 'object',
              'properties': {'id': {'type': 'string'},
                             'occurrenceDate': {'type': 'string', 'format': 'date'}},
              'required': ['id']},
 'list_scheduling_hours': {'type': 'object', 'properties': {}},
 'get_scheduling_hours': {'type': 'object', 'properties': {'id': {'type': 'string'}}, 'required': ['id']}}

# Compatibility updates accept safe partial bodies as well as full records.
SCHEMAS["update_event"]["required"] = ["id"]

_METADATA = {"category", "person", "communication_mode", "tags"}
_READ_FIELDS = {"itemType", "completed", "dateCreated", "lastModified", "url", "parentItemId", "cancelledOccurrenceDates"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _source_id(ident):
    return ident.removeprefix("flowsavvy:")


def _instant(value):
    date = datetime.fromisoformat(value)
    if date.utcoffset() is None:
        raise ValueError("modifiedAfter must include a UTC offset")
    return date.astimezone(timezone.utc)


class Compat:
    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS compat_items(id TEXT PRIMARY KEY,target_id TEXT,kind TEXT NOT NULL,body TEXT NOT NULL,last_modified TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS compat_lists(alias TEXT PRIMARY KEY,title TEXT NOT NULL)")
            # Capture source aliases once, before later individual task moves.
            snapshot, archived = self._archive(db)
            current = {t["id"]: t for t in store._tasks(db)}
            mapping = {}
            for item in archived.values():
                task = current.get("flowsavvy:" + item["id"])
                if task:
                    mapping.setdefault(item.get("listId", "inbox"), set()).add(task["list"])
            for item in snapshot.get("list_lists", {}).get("lists", []):
                candidates = mapping.get(item["id"], {item["title"]})
                if len(candidates) != 1:
                    # Ambiguous aliases cannot silently point to arbitrary lists.
                    continue
                db.execute("INSERT OR IGNORE INTO compat_lists VALUES(?,?)", (item["id"], next(iter(candidates))))
            db.execute("INSERT OR IGNORE INTO compat_lists VALUES('inbox','Inbox')")

    def tools(self):
        return {"tools": [{"name": name, "description": "Local compatibility: " + name.replace("_", " ") + ". Recurrence mutations are unsupported.", "inputSchema": deepcopy(schema)} for name, schema in sorted(SCHEMAS.items())]}

    def _archive(self, db):
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='migration_snapshot' AND type='table'").fetchone():
            return {}, {}
        row = db.execute("SELECT body FROM migration_snapshot LIMIT 1").fetchone()
        snapshot = json.loads(row[0]) if row else {}
        archived = {r["source_id"]: json.loads(r["body"]) for r in db.execute("SELECT source_id,body FROM migration_items")}
        return snapshot, archived

    def _catalog(self, db, snapshot):
        aliases = {row["alias"]: row["title"] for row in db.execute("SELECT * FROM compat_lists")}
        native_titles = {t["list"] for t in self.store._tasks(db)} | set(aliases.values())
        source = {item["id"]: item for item in snapshot.get("list_lists", {}).get("lists", [])}
        lists = {}
        for title in sorted(native_titles):
            ids = sorted(alias for alias, target in aliases.items() if target == title)
            preferred = next((ident for ident in ids if source.get(ident, {}).get("title") == title), None)
            ident = preferred or (ids[0] if ids else "native-list:" + hashlib.sha256(title.encode()).hexdigest()[:20])
            lists[ident] = dict(source.get(ident, {}), id=ident, title=title)
            aliases.setdefault(ident, title)
        default = snapshot.get("list_lists", {}).get("defaultListId", "inbox")
        canonical = {row["title"]: ident for ident, row in lists.items()}
        default = canonical.get(aliases.get(default), "inbox")
        return lists, aliases, canonical, default

    def _project(self, task, original, aliases, canonical, modified):
        raw = dict(original)
        ident = _source_id(task["id"])
        zone = task.get("time_zone") or self.store.zone
        def wall(value):
            return datetime.fromisoformat(value).astimezone(ZoneInfo(zone)).replace(tzinfo=None).isoformat() if value else None
        list_id = raw.get("listId")
        if aliases.get(list_id) != task["list"]:
            list_id = canonical[task["list"]]
        raw.update(id=ident, itemType="task", title=task["title"], notes=task["notes"],
                   listId=list_id, completed=task["completed"], progressMinutes=task["progress"],
                   durationMinutes=task["minutes"], priority=("low", "normal", "high", "asap")[task["priority"]],
                   dueDateTime=wall(task["due"]), canBeStartedAt=wall(task["earliest"]),
                   startDateTime=wall(task["fixed_start"]),
                   endDateTime=wall((datetime.fromisoformat(task["fixed_start"]) + timedelta(minutes=task["minutes"])).isoformat()) if task["fixed_start"] else None,
                   isAutoScheduled=not bool(task["fixed_start"]), isAutoIgnored=not task["allow_late"],
                   minLengthMinutes=task["min_block"] if task["split"] else task["minutes"],
                   bufferBeforeMinutes=task["buffer"], bufferAfterMinutes=task["buffer"],
                   blockedByIds=[_source_id(value) for value in task["dependencies"]], timeZone=zone,
                   lastModified=modified or raw.get("lastModified") or "1970-01-01T00:00:00+00:00")
        raw.update({key: task.get(key, [] if key == "tags" else "other" if key == "category" else "") for key in _METADATA})
        if getattr(self.store, 'public_url', None):
            raw['url'] = self.store.public_url + '/?task=' + quote(task['id'], safe='')
        raw.setdefault("dateCreated", raw["lastModified"])
        raw.setdefault("recurrenceRule", None)
        return raw

    def _items(self, db):
        snapshot, archived = self._archive(db)
        lists, aliases, canonical, default = self._catalog(db, snapshot)
        raw = dict(archived)
        changes = {}
        for row in db.execute("SELECT * FROM compat_items"):
            raw[row["id"]] = json.loads(row["body"])
            changes[row["target_id"] or row["id"]] = row["last_modified"]
        for row in db.execute("SELECT object_id,MAX(at) AS modified FROM audit GROUP BY object_id"):
            changes[row["object_id"]] = max(changes.get(row["object_id"], ""), row["modified"])
        occurrence_ids = {r[0] for r in db.execute("SELECT task FROM occurrences")}
        native = [t for t in self.store._tasks(db) if t["id"] not in occurrence_ids]
        for row in db.execute("SELECT id,body FROM series"):
            ident = _source_id(row["id"])
            if ident in raw:
                template = json.loads(row["body"])["template"]
                raw[ident] = dict(raw[ident], title=template["title"], notes=template.get("notes", ""))
                raw[ident].update({key: template.get(key, [] if key == "tags" else "other" if key == "category" else "") for key in _METADATA})
                if aliases.get(raw[ident].get("listId")) != template["list"]:
                    raw[ident]["listId"] = canonical[template["list"]]
                if changes.get(row["id"]):
                    raw[ident]["lastModified"] = changes[row["id"]]
        for task in native:
            ident = _source_id(task["id"])
            raw[ident] = self._project(task, raw.get(ident, {}), aliases, canonical, changes.get(task["id"]))
        # Reverse dependency projection reflects current native relationships.
        reverse = {}
        for other in native:
            for predecessor in other["dependencies"]:
                reverse.setdefault(predecessor, []).append(_source_id(other["id"]))
        for task in native:
            raw[_source_id(task["id"])]["blocksIds"] = sorted(reverse.get(task["id"], []))
        for item in raw.values():
            if not item.get("lastModified"):
                item["lastModified"] = snapshot.get("finished_at") or "1970-01-01T00:00:00+00:00"
        return raw, snapshot, lists, aliases, default

    def call(self, tool, args, client, idempotency_key=None):
        if tool not in SCHEMAS:
            raise ValueError("Unsupported compatibility tool: " + str(tool))
        if not isinstance(args, dict):
            raise ValueError("arguments must be an object")
        args = deepcopy(args)
        allowed = set(SCHEMAS[tool]["properties"])
        # Full raw get/update clients sometimes echo source read-only fields.
        if tool in ("update_task", "update_event"):
            allowed |= _READ_FIELDS
        if set(args) - allowed:
            raise ValueError("Unsupported fields: " + ", ".join(sorted(set(args) - allowed)))
        for name in SCHEMAS[tool].get("required", []):
            if name not in args:
                raise ValueError("Missing field: " + name)
        if args.get("occurrenceDate") or args.get("scope"):
            raise ValueError("Occurrence contracts require explicit recurrence reconciliation")
        write = tool.startswith(("create_", "update_")) or tool in ("complete_task", "uncomplete_task")
        key = idempotency_key or str(uuid.uuid4())
        if not isinstance(key, str) or not 1 <= len(key) <= 200:
            raise ValueError("Invalid Idempotency-Key")
        signature = json.dumps(["compat", tool, args], sort_keys=True)
        with self.store.db() as db:
            if write:
                previous = db.execute("SELECT request,result FROM operations WHERE client=? AND key=?", (client, key)).fetchone()
                if previous:
                    if previous["request"] != signature:
                        raise Conflict("Idempotency key was already used for different input")
                    return json.loads(previous["result"])
            items, snapshot, lists, aliases, default = self._items(db)
            if write:
                result, target = self._write(db, tool, args, items, snapshot, lists, aliases, default)
                db.execute("INSERT INTO operations VALUES(?,?,?,?)", (client, key, signature, json.dumps(result)))
                db.execute("INSERT INTO audit(at,action,object_id) VALUES(?,?,?)", (result.get("lastModified", _now()), "compat:" + tool, target))
                db.execute("DELETE FROM plans")
                return result
            if tool == "get_item":
                ident = _source_id(str(args["id"]))
                if ident not in items:
                    if db.execute("SELECT 1 FROM occurrences WHERE task=?", (str(args["id"]),)).fetchone():
                        raise ValueError("Native recurrence occurrences require the native task API")
                    raise KeyError(ident)
                return items[ident]
            if tool == "list_items":
                return self._list(args, items, aliases)
            if tool == "list_lists":
                return {"lists": list(lists.values()), "defaultListId": default}
            if tool == "get_list":
                ident = str(args["id"])
                if ident not in aliases:
                    raise KeyError(ident)
                return dict(next(v for v in lists.values() if v["title"] == aliases[ident]), id=ident)
            if tool == "list_calendars":
                return snapshot.get("list_calendars", {"calendars": [{"id": "native", "title": "Interstice"}], "defaultCalendarId": "native"})
            profiles = snapshot.get("list_scheduling_hours", self._default_hours())
            if tool == "list_scheduling_hours":
                return profiles
            if tool == "get_scheduling_hours":
                value = next((p for p in profiles["schedulingHours"] if p["id"] == args["id"]), None)
                if value is None:
                    raise KeyError(args["id"])
                return value
            raise ValueError("Unsupported compatibility tool")

    def _list(self, args, items, aliases):
        limit = args.get("limit", 50)
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        completed = args.get("completed", False)
        if completed in ("true", "false"):
            completed = completed == "true"
        if type(completed) is not bool:
            raise ValueError("completed must be boolean")
        kind = args.get("itemType")
        if kind not in (None, "task", "event"):
            raise ValueError("Invalid itemType")
        if args.get("listId") and kind != "task" or args.get("calendarId") and kind != "event":
            raise ValueError("List/calendar filters require matching itemType")
        if args.get("listId") and args["listId"] not in aliases:
            raise ValueError("Unknown or ambiguous list alias")
        after = _instant(args["modifiedAfter"]) if args.get("modifiedAfter") else None
        query = str(args.get("query", "")).casefold()
        filters = {k: v for k, v in args.items() if k not in ("pageToken", "limit")}
        digest = hashlib.sha256(json.dumps(filters, sort_keys=True).encode()).hexdigest()
        cursor = ""
        if args.get("pageToken"):
            try:
                token = json.loads(base64.urlsafe_b64decode(args["pageToken"].encode()))
                if token["filter"] != digest:
                    raise ValueError()
                cursor = token["after"]
                if not isinstance(cursor, str):
                    raise ValueError()
            except Exception:
                raise ValueError("Invalid page token for these filters") from None
        selected = []
        for ident, item in sorted(items.items()):
            if ident <= cursor or (kind and item["itemType"] != kind) or bool(item.get("completed", False)) != completed:
                continue
            if args.get("listId") and aliases.get(item.get("listId"), item.get("listId")) != aliases.get(args["listId"], args["listId"]):
                continue
            if args.get("calendarId") and item.get("calendarId") != args["calendarId"]:
                continue
            if query and not any(query in str(item.get(k) or "").casefold() for k in ("title", "notes", "location")):
                continue
            if after and _instant(item.get("lastModified") or "1970-01-01T00:00:00Z") <= after:
                continue
            selected.append(item)
            if len(selected) > limit:
                break
        token = None
        if len(selected) > limit:
            token = base64.urlsafe_b64encode(json.dumps({"filter": digest, "after": selected[limit-1]["id"]}).encode()).decode()
        return {"items": selected[:limit], "nextPageToken": token}

    def _default_hours(self):
        return {"defaultSchedulingHoursId": "native", "schedulingHours": [{"id": "native", "title": "Default", "recurringHours": {day: [{"startTime": "09:00", "endTime": "17:00"}] for day in ("monday", "tuesday", "wednesday", "thursday", "friday")}, "dateOverrides": {}}]}

    def _write(self, db, tool, args, items, snapshot, lists, aliases, default):
        creating = tool.startswith("create_")
        raw_id = "etabli:" + str(uuid.uuid4()) if creating else _source_id(str(args["id"]))
        old = None if creating else items.get(raw_id)
        if not creating and old is None:
            raise KeyError(raw_id)
        kind = "event" if tool.endswith("event") else "task"
        if old and old["itemType"] != kind:
            raise ValueError("Wrong item type")
        if old and tool.startswith("update_"):
            if args.get("lastModified") and args["lastModified"] != old.get("lastModified"):
                raise Conflict("Item changed; refresh before editing")
            for field in ("completed", "cancelledOccurrenceDates", "parentItemId", "itemType"):
                if field in args and args[field] != old.get(field):
                    raise ValueError("Cannot modify read-only field: " + field)
        if any(args.get(k) or (old or {}).get(k) for k in ("parentItemId", "occurrenceDate")):
            raise ValueError("Occurrence mutations require explicit recurrence reconciliation")
        if args.get("recurrenceRule") or (old or {}).get("recurrenceRule"):
            if old and kind == "task" and tool == "update_task":
                return self._write_series(db, args, old)
            raise ValueError("Recurring item mutations require explicit recurrence reconciliation")
        target = next((t["id"] for t in self.store._tasks(db) if _source_id(t["id"]) == raw_id), raw_id)
        now = _now()
        if kind == "event":
            if old:
                self._writable_calendar(old.get("calendarId"), snapshot)
            raw = self._event(dict(old or {}, **args), snapshot)
            raw.update(id=raw_id, itemType="event", completed=False, dateCreated=(old or {}).get("dateCreated", now), lastModified=now)
            db.execute("INSERT INTO compat_items VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,last_modified=excluded.last_modified", (raw_id, None, kind, json.dumps(raw), now))
            return raw, raw_id
        tasks = self.store._tasks(db)
        current = next((t for t in tasks if t["id"] == target), None)
        if not creating and current is None:
            raise ValueError("Archived task is not a writable native task")
        if tool in ("complete_task", "uncomplete_task"):
            task = {k: current.get(k, Task.model_fields[k].get_default(call_default_factory=True)) for k in Task.model_fields}
            task["completed"] = tool == "complete_task"
            raw = dict(old)
        else:
            if "blocksIds" in args and (args.get("blocksIds") or []) != ((old or {}).get("blocksIds") or []):
                raise ValueError("Changing blocksIds is unsupported; update blockedByIds on the dependent task")
            if creating and args.get("progressMinutes", 0):
                raise ValueError("Initial progress must be recorded after creation")
            raw = {k: v for k, v in dict(old or {}, **args).items() if k not in _METADATA | {"id", "scope", "occurrenceDate"} | _READ_FIELDS}
            raw.setdefault("title", "Untitled")
            raw.setdefault("notes", "")
            raw.setdefault("listId", default)
            raw.setdefault("completed", (old or {}).get("completed", False))
            raw.setdefault("durationMinutes", 30)
            raw.setdefault("isAutoScheduled", not bool(raw.get("startDateTime")))
            raw.setdefault("minLengthMinutes", raw["durationMinutes"])
            if raw["listId"] not in aliases:
                raise ValueError("Unknown or ambiguous list alias")
            profiles = snapshot.get("list_scheduling_hours", self._default_hours())
            source_lists = {ident: dict(next((v for v in lists.values() if v["title"] == title), {}), id=ident, title=title) for ident, title in aliases.items()}
            task = map_task(raw, source_lists, {p["id"]: p for p in profiles["schedulingHours"]}, profiles["defaultSchedulingHoursId"], self.store.zone)
            task["dependencies"] = [next((t["id"] for t in tasks if _source_id(t["id"]) == _source_id(str(ident))), str(ident)) for ident in raw.get("blockedByIds") or []]
            if current:
                # Preserve native metadata and controls absent from legacy API.
                for field in _METADATA | {"weekdays", "hours_start", "hours_end"}:
                    task[field] = current.get(field, Task.model_fields[field].get_default(call_default_factory=True))
                if raw.get("listId") == old.get("listId"):
                    task["scheduled"] = current["scheduled"]
                    if raw.get("schedulingHoursId") == old.get("schedulingHoursId"):
                        task["availability"] = current.get("availability")
                        task["date_overrides"] = current.get("date_overrides", {})
            task.update({k: v for k, v in args.items() if k in _METADATA})
            if creating:
                hook = getattr(self.store, "_classify_create", None)
                if hook:
                    for field in _METADATA - set(args):
                        task.pop(field, None)
                    inferred = hook(task)
                    if inferred is not None:
                        task = inferred
        task = Task.model_validate(task).model_dump(mode="json")
        if task["fixed_start"] and task["dependencies"]:
            raise ValueError("Pinned dependencies are unsupported")
        if creating and len(tasks) >= 10000:
            raise ValueError("Instance task limit reached")
        graph_order([t for t in tasks if t["id"] != target] + [dict(task, id=target)])
        progress = args.get("progressMinutes", current["progress"] if current else 0)
        if type(progress) is not int or not 0 <= progress <= 10080:
            raise ValueError("Invalid progressMinutes")
        credited = current["progress"] if current else 0
        if progress < credited:
            raise Conflict("Cumulative progress cannot decrease")
        if progress > credited:
            db.execute("INSERT INTO receipts VALUES(?,?,?,?)", ("compat:progress", str(uuid.uuid4()), target, progress-credited))
        version = current["revision"] + 1 if current else 1
        db.execute("INSERT INTO tasks VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,revision=excluded.revision", (target, json.dumps(task), version))
        # Keep provider-only read fields and display settings through state updates.
        saved = dict(old or {}, **raw)
        saved.update(id=raw_id, itemType="task", dateCreated=(old or {}).get("dateCreated", now), lastModified=now)
        db.execute("INSERT INTO compat_items VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,last_modified=excluded.last_modified", (raw_id, target, kind, json.dumps(saved), now))
        projected = self._project(dict(task, id=target, progress=progress), saved, aliases, {v["title"]: k for k, v in lists.items()}, now)
        return projected, target

    def _write_series(self, db, args, old):
        target = "flowsavvy:" + old["id"]
        row = db.execute("SELECT body FROM series WHERE id=?", (target,)).fetchone()
        if row is None:
            raise ValueError("Recurring task is not a writable native series")
        editable = {"title", "notes", "customColor"} | _METADATA
        for key, value in args.items():
            if key not in editable | _READ_FIELDS | {"id"} and value != old.get(key):
                raise ValueError("Structural recurrence changes require explicit reconciliation: " + key)
        body = json.loads(row[0])
        changed = {k: v for k, v in args.items() if k in editable - {"customColor"}}
        template = dict(body["template"], **changed)
        body["template"] = Task.model_validate(template).model_dump(mode="json")
        # Metadata edits apply to unfinished materialized occurrences, preserving
        # each occurrence's dates, completion state, dependencies and receipts.
        for occurrence in db.execute("SELECT tasks.* FROM tasks JOIN occurrences ON tasks.id=occurrences.task WHERE occurrences.series=?", (target,)).fetchall():
            task = json.loads(occurrence["body"])
            if task["completed"]:
                continue
            task.update(changed)
            task = Task.model_validate(task).model_dump(mode="json")
            db.execute("UPDATE tasks SET body=?,revision=revision+1 WHERE id=?", (json.dumps(task), occurrence["id"]))
            db.execute("INSERT INTO audit(at,action,object_id) VALUES(?,?,?)", (_now(), "compat:series_metadata", occurrence["id"]))
        db.execute("UPDATE series SET body=? WHERE id=?", (json.dumps(body), target))
        raw = dict(old, **{k: v for k, v in args.items() if k in editable})
        raw["lastModified"] = _now()
        db.execute("INSERT INTO compat_items VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,last_modified=excluded.last_modified", (old["id"], target, "task", json.dumps(raw), raw["lastModified"]))
        return raw, target

    def _writable_calendar(self, ident, snapshot):
        calendars = snapshot.get("list_calendars", {}).get("calendars", [{"id": "native", "source": "native"}])
        calendar = next((c for c in calendars if c["id"] == ident), None)
        if calendar is None:
            raise ValueError("Unknown calendar")
        if calendar.get("source") not in (None, "native", "flowsavvy") or calendar.get("readOnly") or calendar.get("isReadOnly"):
            raise ValueError("External or read-only calendars cannot be written through the local compatibility API")

    def _event(self, args, snapshot):
        raw = {k: v for k, v in args.items() if k not in {"id", "scope", "occurrenceDate"} | _READ_FIELDS}
        raw.setdefault("title", "Untitled")
        raw.setdefault("notes", "")
        raw.setdefault("allDay", False)
        raw.setdefault("busy", not raw["allDay"])
        raw.setdefault("calendarId", snapshot.get("list_calendars", {}).get("defaultCalendarId", "native"))
        self._writable_calendar(raw["calendarId"], snapshot)
        if not isinstance(raw["title"], str) or not 1 <= len(raw["title"]) <= 300 or not isinstance(raw["notes"], str) or len(raw["notes"]) > 10000:
            raise ValueError("Invalid event title/notes")
        if type(raw["allDay"]) is not bool or type(raw["busy"]) is not bool:
            raise ValueError("Invalid event flags")
        zone = raw.get("timeZone") or self.store.zone
        zone = self.store.zone if zone == "Floating" else zone
        start, end = (datetime.fromisoformat(local_time(raw.get(k), zone)) for k in ("startDateTime", "endDateTime"))
        if end <= start:
            raise ValueError("Event end must follow start")
        if raw["allDay"] and (any((start.hour, start.minute, start.second, start.microsecond)) or any((end.hour, end.minute, end.second, end.microsecond))):
            raise ValueError("All-day events require midnight boundaries")
        for key in ("bufferBeforeMinutes", "bufferAfterMinutes"):
            raw[key] = raw.get(key) if raw.get(key) is not None else 0
            if type(raw[key]) is not int or not 0 <= raw[key] <= 120:
                raise ValueError("Invalid event buffer")
        raw["timeZone"] = zone
        return raw

    def events(self, db=None):
        """Native and archived provider-local events; external events stay external.

        Root's planner merges these into calendar inputs in the same snapshot
        transaction; do not call this method without db from an open transaction.
        """
        if db is None:
            with self.store.db() as connection:
                return self.events(connection)
        snapshot, archived = self._archive(db)
        local_calendars = {c["id"] for c in snapshot.get("list_calendars", {}).get("calendars", []) if c.get("source") in ("flowsavvy", "native")}
        values = {ident: item for ident, item in archived.items() if item["itemType"] == "event" and item.get("calendarId") in local_calendars}
        for row in db.execute("SELECT id,body FROM compat_items WHERE kind='event' ORDER BY id"):
            values[row["id"]] = json.loads(row["body"])
        events = []
        for raw in values.values():
            if raw.get("recurrenceRule") or raw.get("parentItemId"):
                raise ValueError("Native recurring calendar events require explicit recurrence reconciliation")
            zone = raw.get("timeZone") or self.store.zone
            zone = self.store.zone if zone == "Floating" else zone
            start = datetime.fromisoformat(local_time(raw["startDateTime"], zone)) - timedelta(minutes=raw.get("bufferBeforeMinutes") or 0)
            end = datetime.fromisoformat(local_time(raw["endDateTime"], zone)) + timedelta(minutes=raw.get("bufferAfterMinutes") or 0)
            events.append({"id": raw["id"], "title": raw["title"], "start": start.isoformat(), "end": end.isoformat(), "busy": raw["busy"]})
        return events
