# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
from datetime import datetime, timedelta, timezone, time, date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from bisect import insort, bisect_right
import json
from typing import List
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

UTC = timezone.utc


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=300)
    notes: str = Field(default="", max_length=10000)
    list: str = Field(default="Inbox", min_length=1, max_length=100)
    minutes: int = Field(default=30, ge=1, le=10080)
    priority: int = Field(default=1, ge=0, le=3)
    due: datetime | None = None
    earliest: datetime | None = None
    fixed_start: datetime | None = None
    split: bool = True
    min_block: int = Field(default=15, ge=1, le=480)
    buffer: int = Field(default=0, ge=0, le=120)
    hours_start: int = Field(default=9, ge=0, le=23)
    hours_end: int = Field(default=17, ge=1, le=24)
    weekdays: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], max_length=7)
    dependencies: List[str] = Field(default_factory=lambda: [], max_length=50)
    scheduled: bool = True
    completed: bool = False
    allow_late: bool = False
    time_zone: str | None = None
    availability: dict[str, List[tuple[int, int]]] | None = None
    date_overrides: dict[str, List[tuple[int, int]]] = Field(default_factory=dict)

    @field_validator("due", "earliest", "fixed_start")
    @classmethod
    def aware(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("Use an explicit time-zone offset")
        return value

    @model_validator(mode="after")
    def valid(self):
        if self.time_zone:
            try:
                ZoneInfo(self.time_zone)
            except ZoneInfoNotFoundError:
                raise ValueError('Unknown task time zone') from None
        if len(self.date_overrides) > 3660:
            raise ValueError("Too many availability overrides")
        for key, ranges in (self.availability or {}).items():
            if key not in {str(i) for i in range(7)}:
                raise ValueError("Availability weekdays must be 0 to 6")
        for key in self.date_overrides:
            if date.fromisoformat(key).isoformat() != key:
                raise ValueError('Use ISO dates for availability overrides')
        for ranges in list((self.availability or {}).values()) + list(self.date_overrides.values()):
            if len(ranges) > 24:
                raise ValueError("Too many daily availability windows")
            previous = -1
            for start, end in sorted(ranges):
                if not 0 <= start < end <= 1440 or start < previous:
                    raise ValueError("Invalid or overlapping availability windows")
                previous = end
        if not self.title.strip():
            raise ValueError("Title cannot be blank")
        if self.hours_end <= self.hours_start:
            raise ValueError("Hours must end after they start")
        if any(d not in range(7) for d in self.weekdays):
            raise ValueError("Weekdays must be 0 to 6")
        if self.earliest and self.due and self.due < self.earliest:
            raise ValueError("Deadline is before earliest start")
        return self


def graph_order(tasks):
    by_id = {t["id"]: t for t in tasks}
    visiting, visited, output = set(), set(), []

    # An explicit stack supports the full task limit without Python recursion.
    for root in sorted(tasks, key=lambda x: (-x["priority"], instant(x["due"]).timestamp() if x["due"] else float("inf"), x["id"])):
        stack = [(root, False)]
        while stack:
            t, expanded = stack.pop()
            ident = t["id"]
            if expanded:
                visiting.remove(ident)
                visited.add(ident)
                output.append(t)
                continue
            if ident in visited:
                continue
            if ident in visiting:
                raise ValueError("Dependency cycle")
            visiting.add(ident)
            stack.append((t, True))
            for predecessor in reversed(t["dependencies"]):
                if predecessor not in by_id:
                    raise ValueError("Unknown dependency")
                stack.append((by_id[predecessor], False))
    return output


def instant(text):
    return datetime.fromisoformat(text).astimezone(UTC) if isinstance(text, str) else text.astimezone(UTC)


def working_windows(task, day, zone):
    tz = ZoneInfo(task.get("time_zone") or zone)
    overrides = task.get("date_overrides", {})
    if day.isoformat() in overrides:
        ranges = overrides[day.isoformat()]
    elif task.get("availability") is not None:
        ranges = task["availability"].get(str(day.weekday()), [])
    else:
        ranges = [(task["hours_start"] * 60, task["hours_end"] * 60)] if day.weekday() in task["weekdays"] else []
    midnight = datetime.combine(day, time(), tz)
    return [((midnight + timedelta(minutes=a)).astimezone(UTC),
             (midnight + timedelta(minutes=b)).astimezone(UTC)) for a, b in sorted(ranges)]


def schedule(tasks, events, zone="Europe/Berlin", now=None, days=56, previous=None):
    """Deterministic first-fit test planner. Never publishes calendar writes."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    now = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = now + timedelta(days=days)
    occupied = []
    for start, stop in sorted((instant(e["start"]), instant(e["end"])) for e in events if e.get("busy", True)):
        if occupied and start <= occupied[-1][1]:
            occupied[-1] = (occupied[-1][0], max(stop, occupied[-1][1]))
        else:
            occupied.append((start, stop))
    blocks, shortages, finished = [], [], {}
    window_cache = {}
    order = graph_order(tasks)

    def reserve(t, start, duration):
        stop = start + timedelta(minutes=duration)
        insort(occupied, (start - timedelta(minutes=t["buffer"]), stop + timedelta(minutes=t["buffer"])))
        blocks.append({"task_id": t["id"], "title": t["title"], "start": start.isoformat(),
                       "end": stop.isoformat(), "minutes": duration, "fixed": bool(t["fixed_start"])})
        return stop

    # Reserve pinned work first so flexible work cannot steal its time.
    for t in order:
        remaining = max(0, t["minutes"] - t.get("progress", 0))
        if t["fixed_start"] and t["scheduled"] and not t["completed"] and remaining:
            start = instant(t["fixed_start"])
            stop = start + timedelta(minutes=remaining)
            buffer = timedelta(minutes=t["buffer"])
            conflicts = any(start - buffer < b and stop + buffer > a for a, b in occupied)
            # Pins with dependencies are refused by the API until their semantics are supported.
            if start < now or stop > end or conflicts or (t["due"] and not t.get("allow_late") and stop > instant(t["due"])) or (t["earliest"] and start < instant(t["earliest"])):
                shortages.append({"task_id": t["id"], "title": t["title"], "minutes": remaining, "reason": "Fixed block conflicts or falls outside its permitted interval"})
            else:
                finished[t["id"]] = reserve(t, start, remaining)

    # Reserve still-valid work before allocating new gaps. Dependencies are visited
    # first; if a predecessor must move, its dependants are reconsidered as well.
    prior = {}
    for block in previous or []:
        prior.setdefault(block['task_id'], []).append(block)
    by_id = {t['id']: t for t in tasks}
    for t in order:
        candidates = sorted(prior.get(t['id'], []), key=lambda b: b['start'])
        remaining = max(0, t['minutes'] - t.get('progress', 0))
        if not candidates or t['fixed_start'] or t['completed'] or not t['scheduled'] or not remaining:
            continue
        if sum(b['minutes'] for b in candidates) != remaining or (not t['split'] and len(candidates) != 1):
            continue
        if any(d not in finished and not by_id[d]['completed'] and by_id[d].get('progress', 0) < by_id[d]['minutes'] for d in t['dependencies']):
            continue
        earliest = max([now, instant(t['earliest']) if t['earliest'] else now] + [finished[d] for d in t['dependencies'] if d in finished])
        latest = min(end, instant(t['due']) if t['due'] and not t.get('allow_late') else end)
        pad = timedelta(minutes=t['buffer'])
        intervals = []
        for b in candidates:
            start, stop = instant(b['start']), instant(b['end'])
            day = start.astimezone(ZoneInfo(t.get('time_zone') or zone)).date()
            if (not earliest <= start < stop <= latest or
                (stop-start).total_seconds() != b['minutes']*60 or
                b['minutes'] < min(t['min_block'], remaining) or
                not any(a <= start < stop <= z for a,z in working_windows(t,day,zone)) or
                any(start-pad < z and stop+pad > a for a,z in occupied+intervals)):
                intervals = []
                break
            intervals.append((start-pad, stop+pad))
        if len(intervals) == len(candidates):
            for b in candidates:
                finished[t['id']] = reserve(t, instant(b['start']), b['minutes'])

    for t in order:
        remaining = max(0, t["minutes"] - t.get("progress", 0))
        if t["completed"] or not remaining:
            finished[t["id"]] = now
            continue
        if not t["scheduled"] or t["fixed_start"] or t['id'] in finished:
            continue
        missing = [d for d in t["dependencies"] if d not in finished]
        if missing:
            shortages.append({"task_id": t["id"], "title": t["title"], "minutes": remaining, "reason": "Predecessor is unscheduled or cannot finish"})
            continue
        earliest = max([now, instant(t["earliest"]) if t["earliest"] else now] + [finished[d] for d in t["dependencies"]])
        latest = min(end, instant(t["due"]) if t["due"] and not t.get("allow_late") else end)
        minimum = min(t["min_block"], remaining)
        task_tz = ZoneInfo(t.get("time_zone") or zone)
        window_key = json.dumps([t.get('time_zone'), t.get('availability'), t.get('date_overrides'),
                                 t['weekdays'], t['hours_start'], t['hours_end']], sort_keys=True)
        if window_key not in window_cache:
            window_cache[window_key] = [window for offset in range(days + 1)
                       for window in working_windows(t, now.astimezone(task_tz).date() + timedelta(days=offset), zone)]
        windows = window_cache[window_key]
        for day_start, day_end in windows:
            start = max(earliest, day_start)
            stop = min(latest, day_end)
            if start >= stop:
                continue
            pad = timedelta(minutes=t["buffer"])
            # Each gap is formed from occupied intervals expanded for this task's buffer.
            gaps, cursor = [], start
            # Busy intervals are disjoint and ordered. Seek directly to this
            # window instead of scanning every appointment for every task/day.
            index = max(0, bisect_right(occupied, (start-pad, datetime.max.replace(tzinfo=UTC))) - 1)
            for a, b in occupied[index:]:
                a, b = a - pad, b + pad
                if a >= stop or cursor >= stop:
                    break
                if b <= cursor:
                    continue
                if a > cursor:
                    gaps.append((cursor, min(a, stop)))
                cursor = max(cursor, b)
            if cursor < stop:
                gaps.append((cursor, stop))
            for a, b in gaps:
                capacity = int((b - a).total_seconds() // 60)
                take = min(capacity, remaining)
                if take < remaining and remaining - take < minimum:
                    take = remaining - minimum
                if take <= 0 or (not t["split"] and take < remaining) or take < minimum:
                    continue
                last = reserve(t, a, take)
                remaining -= take
                if not remaining:
                    finished[t["id"]] = last
                    break
            if not remaining:
                break
        if remaining:
            shortages.append({"task_id": t["id"], "title": t["title"], "minutes": remaining, "reason": "Insufficient permitted time before deadline/horizon"})
    blocks.sort(key=lambda b: b["start"])
    allocated_finish = {}
    for block in blocks:
        allocated_finish[block['task_id']] = max(allocated_finish.get(block['task_id'], now), instant(block['end']))
    late = [{"task_id": t["id"], "title": t["title"], "due": t["due"],
             "planned_finish": allocated_finish[t["id"]].isoformat()}
            for t in tasks if t.get("due") and t['id'] in allocated_finish
            and not t["completed"] and allocated_finish[t["id"]] > instant(t["due"])]
    return {"blocks": blocks, "shortages": shortages, "late": late, "calculated_at": now.isoformat(), "horizon_days": days, "time_zone": zone}
