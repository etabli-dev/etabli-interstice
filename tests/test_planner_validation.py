# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
"""Calendar validation retains every busy constraint at large input counts."""
from datetime import datetime, timedelta, timezone
import random
import unittest
from unittest.mock import patch
from app.domain import Task, schedule, instant
from app.validation import validate_plan

NOW = datetime(2026, 11, 23, 7, 59, tzinfo=timezone.utc)


class CalendarValidationTests(unittest.TestCase):
    def setUp(self):
        self.task = dict(Task(title='Work', buffer=5).model_dump(mode='json'),
                         id='one', progress=0)
        self.plan = schedule([self.task], [], now=NOW)
        self.start = instant(self.plan['blocks'][0]['start'])
        self.end = instant(self.plan['blocks'][0]['end'])

    def event(self, start, end, busy=True):
        return dict(start=start.isoformat(), end=end.isoformat(), busy=busy)

    def test_busy_interval_index_matches_exhaustive_conflict_check(self):
        rng = random.Random(463)
        for _ in range(160):
            events = []
            for _ in range(rng.randrange(1, 40)):
                start = self.start + timedelta(minutes=rng.randrange(-240, 240))
                end = start + timedelta(minutes=rng.randrange(0, 360))
                events.append(self.event(start, end, rng.choice([True, True, False])))
            rng.shuffle(events)
            pad = timedelta(minutes=5)
            conflict = any(e['busy'] and self.start-pad < instant(e['end'])
                           and self.end+pad > instant(e['start']) for e in events)
            if conflict:
                with self.assertRaisesRegex(ValueError, 'Calendar conflict'):
                    validate_plan([self.task], events, self.plan)
            else:
                validate_plan([self.task], events, self.plan)

    def test_nested_events_and_touching_buffer_boundaries(self):
        pad = timedelta(minutes=5)
        touching = [self.event(self.start-timedelta(hours=1), self.start-pad),
                    self.event(self.end+pad, self.end+timedelta(hours=1))]
        validate_plan([self.task], touching, self.plan)
        nested = [self.event(self.start-timedelta(hours=1), self.end+timedelta(hours=1)),
                  self.event(self.start-timedelta(minutes=20), self.start-timedelta(minutes=10))]
        with self.assertRaisesRegex(ValueError, 'Calendar conflict'):
            validate_plan([self.task], nested, self.plan)

    def test_calendar_dates_are_not_reparsed_for_every_block(self):
        tasks = [dict(self.task, id=str(i), buffer=0, minutes=1, min_block=1)
                 for i in range(100)]
        plan = schedule(tasks, [], now=NOW)
        events = [self.event(self.start-timedelta(days=3, minutes=i+1),
                             self.start-timedelta(days=3, minutes=i)) for i in range(1000)]
        with patch('app.validation.instant', wraps=instant) as parse:
            validate_plan(tasks, events, plan)
            self.assertLess(parse.call_count, 3 * (len(events) + len(plan['blocks'])))


if __name__ == '__main__':
    unittest.main()
