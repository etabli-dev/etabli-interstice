# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
import json
import tempfile
import unittest
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi.testclient import TestClient
from app.domain import Task, schedule
from app.store import Store, Conflict
from app.main import create_app
from app.calendars import parse

NOW = datetime(2026, 11, 23, 7, 59, tzinfo=timezone.utc)


def task(ident, **fields):
    return dict(Task(title=ident, **fields).model_dump(mode="json"), id=ident, progress=0)


class PlannerTests(unittest.TestCase):
    def test_splits_around_busy_time_and_conserves_effort(self):
        event = {"start": "2026-11-23T09:00:00+00:00", "end": "2026-11-23T10:00:00+00:00"}
        result = schedule([task("a", minutes=120)], [event], now=NOW)
        self.assertEqual(sum(b["minutes"] for b in result["blocks"]), 120)
        self.assertEqual(len(result["blocks"]), 2)
        self.assertFalse(result["shortages"])
        for b in result["blocks"]:
            self.assertTrue(b["end"] <= event["start"] or b["start"] >= event["end"])

    def test_shortage_is_explicit(self):
        result = schedule([task("a", minutes=240, due="2026-11-23T10:00:00+00:00")], [], now=NOW)
        self.assertEqual(result["shortages"][0]["minutes"], 120)

    def test_dependency_order_and_cycle(self):
        result = schedule([task("a", dependencies=["b"], priority=3), task("b")], [], now=NOW)
        self.assertEqual([b["task_id"] for b in result["blocks"]], ["b", "a"])
        with self.assertRaises(ValueError):
            schedule([task("a", dependencies=["b"]), task("b", dependencies=["a"])], [], now=NOW)

    def test_pinned_block_reserved_before_flexible_work(self):
        result = schedule([task("flex", minutes=120), task("pin", fixed_start="2026-11-23T08:30:00+00:00", minutes=30)], [], now=NOW)
        for a, b in zip(result["blocks"], result["blocks"][1:]):
            self.assertLessEqual(a["end"], b["start"])

    def test_unsplittable_and_partial_progress(self):
        a = task("a", minutes=120, split=False)
        a["progress"] = 30
        result = schedule([a], [{"start":"2026-11-23T09:00:00+00:00","end":"2026-11-23T10:00:00+00:00"}], now=NOW)
        self.assertEqual(len(result["blocks"]), 1)
        self.assertEqual(result["blocks"][0]["minutes"], 90)

    def test_buffers_and_multiple_tasks_do_not_overlap(self):
        tasks = [task(str(i), minutes=45, buffer=10) for i in range(30)]
        result = schedule(tasks, [], now=NOW)
        self.assertEqual(sum(b["minutes"] for b in result["blocks"]), 30*45)
        for a, b in zip(result["blocks"], result["blocks"][1:]):
            self.assertGreaterEqual(datetime.fromisoformat(b["start"])-datetime.fromisoformat(a["end"]), timedelta(minutes=20))

    def test_spring_dst_local_working_hours(self):
        result = schedule([task("a", weekdays=[6], hours_start=9, hours_end=10)], [], now=datetime(2026,3,29,0,tzinfo=timezone.utc))
        self.assertTrue(result["blocks"][0]["start"].startswith("2026-03-29T07:00"))

    def test_naive_dates_rejected(self):
        with self.assertRaises(ValueError):
            Task(title="x", due="2026-11-30T12:00:00")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/"test.sqlite")

    def tearDown(self):
        self.tmp.cleanup()

    def create(self):
        return self.store.mutate("one", "create", "create", Task(title="Test").model_dump(mode="json"))

    def test_idempotency_and_conflicting_key(self):
        first = self.create()
        self.assertEqual(first, self.create())
        with self.assertRaises(Conflict):
            self.store.mutate("one", "create", "create", Task(title="Other").model_dump(mode="json"))
        self.assertEqual(len(self.store.tasks()), 1)

    def test_progress_retry_cumulative_and_restore(self):
        t = self.create()
        for key in ("p1", "p2"):
            self.store.mutate("phone", key, "progress", {"session_id":"session", "minutes":25}, ident=t["id"])
        self.assertEqual(self.store.tasks()[0]["progress"],25)
        self.store.mutate("phone", "p3", "progress", {"session_id":"session", "minutes":30}, ident=t["id"])
        target = Path(self.tmp.name)/"backup.sqlite"
        self.store.backup(target)
        restored = Store(target)
        self.assertEqual(restored.tasks()[0]["progress"],30)
        self.assertEqual(restored.operation("phone", "p3")["progress"],30)

    def test_stale_revision_and_invalid_update(self):
        t = self.create()
        with self.assertRaises(Conflict):
            self.store.mutate("one", "x", "complete", {}, ident=t["id"], revision=0)
        with self.assertRaises(ValueError):
            self.store.mutate("one", "x", "update", {"mystery":1}, ident=t["id"], revision=1)
        self.assertFalse(self.store.tasks()[0]["completed"])

    def test_failed_calendar_refresh_retains_busy_snapshot(self):
        self.store.source_result("a", [{"start":"2026-11-23T09:00:00+00:00","end":"2026-11-23T10:00:00+00:00"}])
        self.store.source_result("a", error="offline")
        result=self.store.plan(now=NOW)
        self.assertEqual(len(result["events"]),1)
        self.assertEqual(result["sources"][0]["error"],"offline")


class CalendarTests(unittest.TestCase):
    def test_recurrence_and_dst(self):
        ics = 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:test\r\nDTSTART;TZID=Europe/Berlin:20260328T090000\r\nDTEND;TZID=Europe/Berlin:20260328T100000\r\nRRULE:FREQ=DAILY;COUNT=3\r\nSUMMARY:Test\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'
        events=parse([ics], {"id":"test"}, now=datetime(2026,3,28,tzinfo=timezone.utc))
        self.assertEqual(len(events),3)
        self.assertIn('T08:00',events[0]["start"])
        self.assertIn('T07:00',events[1]["start"])

    def test_high_frequency_recurrence_rejected(self):
        ics = 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:test\r\nDTSTART:20261123T090000Z\r\nDTEND:20261123T100000Z\r\nRRULE:FREQ=SECONDLY\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'
        with self.assertRaises(ValueError):
            parse([ics],{"id":"test"},now=NOW)


class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app({"data":self.tmp.name,"public_url":"http://testserver","clients":[
            {"id":"test-admin","token":"a"*40,"role":"admin"},{"id":"test-reader","token":"b"*40,"role":"read"}]})
        self.client=TestClient(self.app)
        self.client.__enter__()
        self.headers={"Authorization":"Bearer "+"a"*40,"Idempotency-Key":"create"}

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.tmp.cleanup()

    def test_auth_scope_and_test_boundary(self):
        self.assertEqual(self.client.get('/api/v1/tasks').status_code,401)
        self.assertEqual(self.client.post('/api/v1/tasks',json={"title":"a"},headers={"Authorization":"Bearer "+"b"*40}).status_code,403)
        self.assertEqual(self.client.post('/api/v1/tasks',json={"title":"a"},headers=self.headers).status_code,200)
        self.assertFalse(self.client.get('/api/v1/schedule',headers=self.headers).json()['calendar_writes'])
        self.assertEqual(self.client.post('/api/v1/calendars/publish',headers=self.headers).status_code,404)

    def test_cookie_csrf_and_logout(self):
        response=self.client.post('/login',json={"token":"a"*40},headers={"Origin":"http://testserver"})
        self.assertEqual(response.status_code,200)
        self.assertIn('HttpOnly',response.headers['set-cookie'])
        self.assertEqual(self.client.post('/api/v1/tasks',json={"title":"a"}).status_code,403)
        self.assertEqual(self.client.post('/api/v1/logout',json={},headers={"Origin":"http://testserver"}).status_code,200)
        self.assertEqual(self.client.get('/api/v1/tasks').status_code,401)

    def test_progress_and_stale_completion(self):
        t=self.client.post('/api/v1/tasks',json={"title":"a"},headers=self.headers).json()
        h={**self.headers,"Idempotency-Key":"p"}
        body={"session_id":"focus-session","minutes":25}
        for _ in range(2):
            response=self.client.post(f'/api/v1/tasks/{t["id"]}/progress',json=body,headers=h)
            self.assertEqual(response.json()['progress'],25)
        response=self.client.post(f'/api/v1/tasks/{t["id"]}/complete',json={},headers={**h,"Idempotency-Key":"c","If-Match":"1"})
        self.assertEqual(response.status_code,409)

    def test_model_disabled_no_mutation(self):
        self.assertEqual(self.client.post('/api/v1/model/propose',json={"text":"test"},headers=self.headers).status_code,503)
        self.assertEqual(self.app.state.store.tasks(),[])

    def test_stripped_proxy_prefix_serves_assets_and_api(self):
        app=create_app({"data":self.tmp.name,"public_url":"http://testserver/trial","clients":[{"id":"test-admin","token":"a"*40,"role":"admin"}]})
        with TestClient(app) as client:
            self.assertEqual(client.get('/').status_code,200)
            self.assertEqual(client.get('/static/app.js').status_code,200)
            self.assertEqual(client.get('/trial/static/style.css').status_code,200)
            self.assertEqual(client.get('/api/v1/status',headers=self.headers).status_code,200)

    def test_mcp_initialize_and_scope(self):
        headers={**self.headers,"Accept":"application/json, text/event-stream"}
        init={"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"test","version":"1"}}}
        response=self.client.post('/mcp',json=init,headers=headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('serverInfo',response.json()['result'])
        headers['MCP-Protocol-Version']='2025-11-25'
        call={"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"task_create","arguments":{"task":{"title":"MCP test"},"idempotency_key":"mcp-create"}}}
        response=self.client.post('/mcp',json=call,headers=headers)
        self.assertFalse(response.json()['result'].get('isError'),response.text)
        self.assertEqual(len(self.app.state.store.tasks()),1)
        headers['Authorization']='Bearer '+'b'*40
        response=self.client.post('/mcp',json=call,headers=headers)
        self.assertTrue(response.json()['result'].get('isError'),response.text)
        self.assertEqual(len(self.app.state.store.tasks()),1)


if __name__ == '__main__':
    unittest.main()
