# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
"""An operation must not depend on the other worker's processing stack."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from app.domain import Task


class WorkerImportIsolationTests(unittest.TestCase):
    def run_isolated(self, operation, payload, unavailable):
        guard = """
import importlib.abc
import runpy
import sys
class Unavailable(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in BLOCKED):
            raise ImportError('Unrelated operation dependency unavailable')
sys.meta_path.insert(0, Unavailable())
runpy.run_module('app.worker', run_name='__main__')
"""
        environment = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "LANG")}
        environment.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, "-c", "BLOCKED = " + repr(unavailable) + guard],
                                input=json.dumps({"operation": operation, "payload": payload}),
                                text=True, capture_output=True, timeout=10,
                                cwd=Path(__file__).resolve().parents[1], env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertTrue(response["ok"])
        return response["result"]

    def test_scheduling_works_without_calendar_or_http_stack(self):
        task = dict(Task(title="Synthetic task").model_dump(mode="json"), id="synthetic", progress=0)
        result = self.run_isolated("schedule", {"tasks": [task], "events": [], "now": "2026-11-30T08:00:00+00:00"},
                                   ["app.calendars", "httpx", "icalendar", "recurring_ical_events"])
        self.assertEqual(sum(block["minutes"] for block in result["blocks"]), 30)
        self.assertEqual(result["shortages"], [])

    def test_calendar_decode_works_without_scheduling_or_validation_stack(self):
        result = self.run_isolated("calendar", {"data": "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n", "method": "GET", "source": {"id": "synthetic"}},
                                   ["app.domain", "app.validation", "pydantic"])
        self.assertEqual(result, [])
