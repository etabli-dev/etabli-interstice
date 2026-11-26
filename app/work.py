# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
"""Bound expensive calculations without blocking the service event loop."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

_slots = threading.BoundedSemaphore(1)


class WorkLimit(RuntimeError):
    pass


def run_job(operation, payload, timeout=30):
    if not _slots.acquire(blocking=False):
        raise WorkLimit("Calculation busy; retry shortly")
    try:
        environment = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "LANG")}
        environment.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
        try:
            result = subprocess.run([sys.executable, "-m", "app.worker"],
                input=json.dumps({"operation": operation, "payload": payload}), text=True,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout,
                cwd=Path(__file__).resolve().parent.parent, env=environment, check=False)
        except subprocess.TimeoutExpired:
            raise WorkLimit("Calculation deadline exceeded") from None
        if result.returncode != 0:
            raise WorkLimit("Calculation exceeded resource limits or failed")
        if len(result.stdout) > 12_000_000:
            raise WorkLimit("Calculation result exceeds limit")
        response = json.loads(result.stdout)
        if not response["ok"]:
            raise ValueError("Invalid calendar or scheduling input")
        return response["result"]
    finally:
        _slots.release()
