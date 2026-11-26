# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded recurring task occurrences with stable identities and wall-clock dates."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import uuid
from dateutil.rrule import rrulestr
from .domain import Task


def occurrences(series, now, days=56):
    template = Task.model_validate(series['template']).model_dump(mode='json')
    if template['dependencies']:
        raise ValueError('Series dependencies require explicit occurrence mapping')
    rule = series['rule']
    parts = dict(part.split('=', 1) for part in rule.split(';'))
    if parts.get('FREQ') not in ('DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY'):
        raise ValueError('Unsupported task recurrence frequency')
    allowed = {'FREQ', 'INTERVAL', 'COUNT', 'UNTIL', 'BYDAY', 'BYMONTHDAY', 'BYMONTH', 'BYSETPOS', 'WKST'}
    if set(parts) - allowed or len(rule) > 500:
        raise ValueError('Unsupported task recurrence rule')
    tz = ZoneInfo(template['time_zone'] or series['zone'])
    anchor = datetime.fromisoformat(series['anchor']).astimezone(tz)
    # dateutil preserves local wall time through DST when dtstart uses ZoneInfo.
    recurring = rrulestr(rule, dtstart=anchor)
    lower = max(anchor, (now - timedelta(days=1)).astimezone(tz))
    upper = (now + timedelta(days=days)).astimezone(tz)
    cancelled = set(series.get('cancelled', []))
    result = []
    for index, value in enumerate(recurring.xafter(lower, inc=True)):
        if value > upper:
            break
        if index >= 1000:
            raise ValueError('Task recurrence expansion limit exceeded')
        if value.date().isoformat() in cancelled:
            continue
        # Reject nonexistent wall-clock dates rather than silently shifting an occurrence.
        if value.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) != value.replace(tzinfo=None):
            raise ValueError('Recurring task falls in a nonexistent local time')
        item = dict(template)
        delta = value.replace(tzinfo=None) - anchor.replace(tzinfo=None)
        for field in ('due', 'earliest', 'fixed_start'):
            if item[field]:
                original = datetime.fromisoformat(item[field]).astimezone(tz)
                item[field] = (original + delta).isoformat()
        item['completed'] = False
        key = value.date().isoformat()
        ident = str(uuid.uuid5(uuid.NAMESPACE_URL, 'interstice:series:' + series['id'] + ':' + key))
        result.append((ident, Task.model_validate(item).model_dump(mode='json'), key))
    return result
