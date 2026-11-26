# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
"""One calculation per disposable Linux worker; no credentials in its input."""
import json
import resource
import sys


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (5, 6))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    request = json.load(sys.stdin)
    try:
        if request["operation"] == "calendar":
            from .calendars import decode
            result = decode(**request["payload"])
        elif request["operation"] == "schedule":
            from .domain import schedule
            from datetime import datetime
            payload = request["payload"]
            payload["now"] = datetime.fromisoformat(payload["now"])
            result = schedule(**payload)
            from .validation import validate_plan
            validate_plan(payload["tasks"], payload["events"], result)
        else:
            raise ValueError("Unknown calculation")
        print(json.dumps({"ok": True, "result": result}))
    except (ValueError, KeyError, TypeError, OverflowError):
        print(json.dumps({"ok": False}))


if __name__ == "__main__":
    main()
