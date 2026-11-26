# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
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

    @field_validator("due", "earliest", "fixed_start")
    @classmethod
    def aware(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("Use an explicit time-zone offset")
        return value

    @model_validator(mode="after")
    def valid(self):
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


def schedule(tasks, events, zone="Europe/Berlin", now=None, days=56):
    """Deterministic first-fit test planner. Never publishes calendar writes."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    now = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = now + timedelta(days=days)
    tz = ZoneInfo(zone)
    occupied = [(instant(e["start"]), instant(e["end"])) for e in events if e.get("busy", True)]
    blocks, shortages, finished = [], [], {}
    order = graph_order(tasks)

    def reserve(t, start, duration):
        stop = start + timedelta(minutes=duration)
        occupied.append((start - timedelta(minutes=t["buffer"]), stop + timedelta(minutes=t["buffer"])))
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
            if start < now or stop > end or conflicts or (t["due"] and stop > instant(t["due"])) or (t["earliest"] and start < instant(t["earliest"])):
                shortages.append({"task_id": t["id"], "title": t["title"], "minutes": remaining, "reason": "Fixed block conflicts or falls outside its permitted interval"})
            else:
                finished[t["id"]] = reserve(t, start, remaining)

    for t in order:
        remaining = max(0, t["minutes"] - t.get("progress", 0))
        if t["completed"] or not remaining:
            finished[t["id"]] = now
            continue
        if not t["scheduled"] or t["fixed_start"]:
            continue
        missing = [d for d in t["dependencies"] if d not in finished]
        if missing:
            shortages.append({"task_id": t["id"], "title": t["title"], "minutes": remaining, "reason": "Predecessor is unscheduled or cannot finish"})
            continue
        earliest = max([now, instant(t["earliest"]) if t["earliest"] else now] + [finished[d] for d in t["dependencies"]])
        latest = min(end, instant(t["due"]) if t["due"] else end)
        minimum = min(t["min_block"], remaining)
        for offset in range(days + 1):
            day = now.astimezone(tz).date() + timedelta(days=offset)
            if day.weekday() not in t["weekdays"]:
                continue
            start = max(earliest, datetime.combine(day, time(t["hours_start"]), tz).astimezone(UTC))
            day_end = datetime.combine(day + timedelta(days=t["hours_end"] == 24), time(t["hours_end"] % 24), tz).astimezone(UTC)
            stop = min(latest, day_end)
            pad = timedelta(minutes=t["buffer"])
            # Each gap is formed from occupied intervals expanded for this task's buffer.
            gaps, cursor = [], start
            for a, b in sorted(occupied):
                a, b = a - pad, b + pad
                if b <= cursor or a >= stop:
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
    return {"blocks": blocks, "shortages": shortages, "calculated_at": now.isoformat(), "horizon_days": days, "time_zone": zone}
