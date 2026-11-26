# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
"""One process owns a database directory for the complete server lifetime."""
import fcntl
import os
from pathlib import Path
import uvicorn


def main():
    os.umask(0o077)
    data = Path(os.environ.get("INTERSTICE_DATA", "/data"))
    data.mkdir(parents=True, exist_ok=True)
    with (data / ".writer.lock").open("a") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another server owns this data directory")
        uvicorn.run("app.main:create_app", factory=True, host="0.0.0.0", port=8080,
                    workers=1, access_log=False, proxy_headers=False, limit_concurrency=8,
                    timeout_keep_alive=5, timeout_graceful_shutdown=30)


if __name__ == "__main__":
    main()
