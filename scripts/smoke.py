#!/usr/bin/env python3
# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
"""Exercise only a test instance. Credentials are read from a file, never printed."""
import argparse
import json
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8080")
parser.add_argument("--tokens", default="/run/secrets/tokens.json")
parser.add_argument("--model", action="store_true")
args = parser.parse_args()
clients = json.loads(Path(args.tokens).read_text())
token = next(c["token"] for c in clients if c["role"] == "admin")


def call(path, body=None, key=None):
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    if key:
        headers["Idempotency-Key"] = key
    request = urllib.request.Request(args.base_url.rstrip("/") + path, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(request, timeout=135) as response:
        return json.load(response)


status = call("/api/v1/status")
assert status["mode"] == "test" and status["calendar_writes"] is False, "Refusing a non-test target"
for index, (title, minutes, priority) in enumerate([
    ("TEST · Outline a workshop", 90, 2), ("TEST · Read a research paper", 45, 1), ("TEST · Review the weekly plan", 20, 0)
]):
    task = call("/api/v1/tasks", {"title": title, "minutes": minutes, "priority": priority, "list": "Test work"}, f"smoke-seed-{index}")
    if index == 0:
        for _ in range(2):
            result = call(f'/api/v1/tasks/{task["id"]}/progress', {"session_id": "smoke-session", "minutes": 25}, "smoke-progress")
            assert result["progress"] == 25
sources = call("/api/v1/calendars/refresh", {})
assert sources and all(s["synced"] and not s["error"] for s in sources), sources
plan = call("/api/v1/schedule")
assert plan["blocks"] and plan["events"] and plan["calendar_writes"] is False
for block in plan["blocks"]:
    for event in plan["events"]:
        assert not event["busy"] or block["end"] <= event["start"] or block["start"] >= event["end"]
report = {"mode": status["mode"], "calendar_writes": False, "tasks": len(call('/api/v1/tasks')["tasks"]),
          "blocks": len(plan["blocks"]), "calendar_events": len(plan["events"]), "duplicate_progress": "passed", "sources": sources}
if args.model:
    before = len(call('/api/v1/tasks')["tasks"])
    proposal = call('/api/v1/model/propose', {"text": "Draft a task called Test the calendar connection, taking 20 minutes. No deadline."})
    assert proposal["applied"] is False and proposal["proposal"]["minutes"] > 0
    assert len(call('/api/v1/tasks')["tasks"]) == before
    report["model_proposal"] = "passed; no task created"
print(json.dumps(report, indent=2))
