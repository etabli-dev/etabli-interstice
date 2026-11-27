# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
"""One calculation per disposable Linux worker; no credentials in its input."""
import json
import math
import resource
import sys


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (15, 40))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    request = json.load(sys.stdin)
    # Bound trusted imports separately from processing untrusted input.
    if request["operation"] == "calendar":
        from .calendars import decode
    elif request["operation"] == "schedule":
        from .domain import schedule
        from .validation import validate_plan
    from datetime import datetime, timezone
    usage = resource.getrusage(resource.RUSAGE_SELF)
    used = math.ceil(usage.ru_utime + usage.ru_stime)
    budget = 15 if request["operation"] == "calendar" else 5
    resource.setrlimit(resource.RLIMIT_CPU, (used + budget, used + budget + 1))
    try:
        if request["operation"] == "calendar":
            result = decode(**request["payload"])
        elif request["operation"] == "schedule":
            payload = request["payload"]
            payload["now"] = datetime.fromisoformat(payload["now"]) if payload["now"] else datetime.now(timezone.utc)
            result = schedule(**payload)
            validate_plan(payload["tasks"], payload["events"], result)
        else:
            raise ValueError("Unknown calculation")
        print(json.dumps({"ok": True, "result": result}))
    except (ValueError, KeyError, TypeError, OverflowError):
        print(json.dumps({"ok": False}))


if __name__ == "__main__":
    main()
