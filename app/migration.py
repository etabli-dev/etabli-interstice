# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline FlowSavvy snapshot import. Original records stay in a private archive.

Contract: https://my.flowsavvy.app/api/docs/public/openapi.json
No provider writes or credentials are involved. Import requires a new database.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo
from .domain import Task, graph_order
from .store import Store
from .recurrence import occurrences


def snapshot_items(snapshot):
    if snapshot.get('format') != 'flowsavvy-mcp-export-v1' or not snapshot.get('finished_at'):
        raise ValueError('Incomplete or unsupported export')
    seen = {}
    collections = set()
    for collection in snapshot['collections']:
        key = (collection['kind'], collection['completed'])
        if key in collections:
            raise ValueError('Duplicate export collection')
        collections.add(key)
        pages = collection['pages']
        if not pages or pages[-1].get('nextPageToken'):
            raise ValueError('Incomplete pagination')
        tokens = set()
        local_ids = set()
        for index, page in enumerate(pages):
            token = page.get('nextPageToken')
            if index < len(pages)-1 and (not token or token in tokens):
                raise ValueError('Invalid pagination chain')
            tokens.add(token)
            for item in page['items']:
                if not isinstance(item.get('id'), str) or not item['id'] or item.get('itemType') != key[0]:
                    raise ValueError('Invalid exported item identity')
                if item['id'] in local_ids:
                    raise ValueError('Duplicate item inside paginated collection')
                local_ids.add(item['id'])
                if key[0] == 'task' and item['completed'] != key[1]:
                    raise ValueError('Task completion changed during export')
                old = seen.get(item['id'])
                if old is not None and old != item:
                    raise ValueError('Item changed during export; collect again')
                seen[item['id']] = item
    if collections != {('task', False), ('task', True), ('event', False), ('event', True)}:
        raise ValueError('Export must include open/completed tasks and events')
    return list(seen.values())


def local_time(value, zone):
    if value is None:
        return None
    dt = datetime.fromisoformat(value)
    if dt.utcoffset() is not None:
        return dt.isoformat()
    tz = ZoneInfo(zone)
    a, b = dt.replace(tzinfo=tz, fold=0), dt.replace(tzinfo=tz, fold=1)
    if a.utcoffset() != b.utcoffset() or a.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) != dt:
        raise ValueError('Ambiguous or nonexistent source wall time requires reconciliation')
    return a.isoformat()


def hours(profile):
    def minute(value, end=False):
        h, m = map(int, value.split(':'))
        if not 0 <= h < 24 or not 0 <= m < 60:
            raise ValueError('Invalid source availability time')
        return 1440 if end and h == m == 0 else h*60+m
    def ranges(rows):
        return [(minute(r['startTime']), minute(r['endTime'], True)) for r in rows or []]
    names = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')
    weekly = profile.get('recurringHours') or {}
    return ({str(i): ranges(weekly.get(name)) for i, name in enumerate(names)},
            {date: ranges(rows) for date, rows in (profile.get('dateOverrides') or {}).items()})


def map_task(item, lists, profiles, default_profile, zone):
    task_zone = item.get('timeZone')
    task_zone = zone if not task_zone or task_zone == 'Floating' else task_zone
    list_id = item['listId']
    if list_id != 'inbox' and list_id not in lists:
        raise ValueError('Task references an absent list')
    lst = lists.get(list_id, {'title': 'Inbox'})
    profile_id = item.get('schedulingHoursId') or lst.get('schedulingHoursId') or default_profile
    if profile_id not in profiles:
        raise ValueError('Task references absent scheduling hours')
    availability, overrides = hours(profiles[profile_id])
    fixed = item.get('isAutoScheduled') is False
    start = local_time(item.get('startDateTime'), task_zone) if fixed else None
    duration = item.get('durationMinutes')
    if fixed:
        end = local_time(item.get('endDateTime'), task_zone)
        if not start or not end:
            raise ValueError('Fixed task lacks interval')
        duration = (datetime.fromisoformat(end).astimezone(timezone.utc) - datetime.fromisoformat(start).astimezone(timezone.utc)).total_seconds()/60
        if int(duration) != duration:
            raise ValueError('Sub-minute task interval is unsupported')
        duration = int(duration)
    before, after = item.get('bufferBeforeMinutes') or 0, item.get('bufferAfterMinutes') or 0
    if before != after:
        raise ValueError('Asymmetric source buffers require reconciliation')
    minimum = item.get('minLengthMinutes') or duration
    task = Task(title=item['title'], notes=item.get('notes') or '', list=lst['title'],
                minutes=duration, priority={'low': 0, 'normal': 1, 'high': 2, 'asap': 3}[item.get('priority') or 'normal'],
                due=local_time(item.get('dueDateTime'), task_zone),
                earliest=local_time(item.get('canBeStartedAt'), task_zone), fixed_start=start,
                split=minimum < duration, min_block=min(minimum, duration, 480), buffer=before,
                dependencies=['flowsavvy:'+ident for ident in item.get('blockedByIds') or []],
                scheduled=list_id != 'inbox', completed=item['completed'], allow_late=not bool(item.get('isAutoIgnored')),
                time_zone=task_zone, availability=availability, date_overrides=overrides)
    return task.model_dump(mode='json')


def prepare(snapshot, zone='Europe/Berlin', now=None):
    now = now or datetime.now(timezone.utc)
    items = snapshot_items(snapshot)
    lists = {v['id']: v for v in snapshot['list_lists']['lists']}
    profiles = {v['id']: v for v in snapshot['list_scheduling_hours']['schedulingHours']}
    default_profile = snapshot['list_scheduling_hours']['defaultSchedulingHoursId']
    tasks, series, progress = [], [], {}
    for item in items:
        if item['itemType'] != 'task':
            continue
        if item.get('parentItemId') or item.get('occurrenceDate'):
            raise ValueError('Edited source recurrence needs explicit exception mapping')
        task = map_task(item, lists, profiles, default_profile, zone)
        ident = 'flowsavvy:'+item['id']
        credited = item.get('progressMinutes') or 0
        if type(credited) is not int or not 0 <= credited <= 10080:
            raise ValueError('Invalid source progress')
        if item.get('recurrenceRule'):
            if credited or task['completed']:
                raise ValueError('Series-level progress needs occurrence reconciliation')
            value = {'id': ident, 'template': task, 'rule': item['recurrenceRule'],
                     'anchor': task['fixed_start'] or task['due'], 'zone': zone,
                     'cancelled': item.get('cancelledOccurrenceDates') or []}
            occurrences(value, now)
            series.append(value)
        else:
            tasks.append(dict(task, id=ident))
            progress[ident] = credited
    if len(tasks) > 10000:
        raise ValueError('Migration exceeds instance task limit')
    graph_order(tasks)
    return items, tasks, series, progress


def import_snapshot(source, destination, zone='Europe/Berlin', list_map=None):
    source, destination = Path(source), Path(destination)
    raw = source.read_bytes()
    snapshot = json.loads(raw)
    items, tasks, series, progress = prepare(snapshot, zone)
    list_map = list_map or {}
    if not isinstance(list_map, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not v.strip() or len(v) > 100 for k, v in list_map.items()):
        raise ValueError('List mapping must contain nonempty names of at most 100 characters')
    for task in tasks + [value['template'] for value in series]:
        task['list'] = list_map.get(task['list'], task['list'])
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Exclusive creation prevents accidental imports into an existing or live instance.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        store = Store(destination, zone)
        with store.db() as db:
            db.execute('CREATE TABLE migration_snapshot(sha256 TEXT PRIMARY KEY, body BLOB NOT NULL)')
            db.execute('CREATE TABLE migration_items(source_id TEXT PRIMARY KEY, target_id TEXT, kind TEXT, body TEXT NOT NULL)')
            digest = hashlib.sha256(raw).hexdigest()
            db.execute('INSERT INTO migration_snapshot VALUES(?,?)', (digest, raw))
            for item in items:
                db.execute('INSERT INTO migration_items VALUES(?,?,?,?)', (item['id'], 'flowsavvy:'+item['id'] if item['itemType']=='task' else None, item['itemType'], json.dumps(item)))
            for task in tasks:
                task = dict(task)
                ident = task.pop('id')
                db.execute('INSERT INTO tasks VALUES(?,?,1)', (ident, json.dumps(task)))
                if progress[ident]:
                    db.execute('INSERT INTO receipts VALUES(?,?,?,?)', ('migration:flowsavvy', ident, ident, progress[ident]))
            for value in series:
                db.execute('INSERT INTO series VALUES(?,?)', (value['id'], json.dumps(value)))
            store._materialize(db, datetime.now(timezone.utc))
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Migration integrity check failed')
        report = {'source_sha256': digest, 'source_items': dict(Counter(i['itemType'] for i in items)),
                  'imported_standalone_tasks': len(tasks), 'recurring_series': len(series),
                  'stored_tasks_with_occurrences': len(store.tasks()),
                  'credited_minutes': sum(progress.values()), 'calendar_events_archived_only': True,
                  'production_ready': False, 'list_mapping': list_map}
        return report
    except BaseException:
        for suffix in ('', '-wal', '-shm'):
            Path(str(destination)+suffix).unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--zone', default='Europe/Berlin')
    parser.add_argument('--list-map', type=Path, help='Explicit JSON mapping of source list names; source archive remains unchanged')
    args = parser.parse_args()
    print(json.dumps(import_snapshot(args.source, args.database, args.zone, json.loads(args.list_map.read_text()) if args.list_map else None), indent=2))


if __name__ == '__main__':
    main()
