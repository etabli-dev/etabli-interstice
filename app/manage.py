# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline restore and consistent online backup; never handles provider credentials."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile


def checked_backup(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists() or source.resolve() == destination.resolve():
        raise ValueError("Backup destination must be new")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".backup-", dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        with sqlite3.connect(source.resolve().as_uri()+"?mode=ro", uri=True) as src, sqlite3.connect(temporary) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup integrity check failed")
            tables = {row[0] for row in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            counts = {t: dst.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in
                      ("tasks", "receipts", "operations", "series", "occurrences", "migration_items", "migration_snapshot") if t in tables}
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        # Linking fails if another backup has already claimed this destination.
        os.link(temporary, destination)
        directory = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        with destination.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        return {"integrity": "ok", "sha256": digest, "counts": counts}
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.action == "restore":
        # Restore only into an empty stopped instance; never overwrite a live database or WAL.
        args.destination.parent.mkdir(parents=True, exist_ok=True)
        with (args.destination.parent / ".writer.lock").open("a") as lease:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if any(Path(str(args.destination)+suffix).exists() for suffix in ("", "-wal", "-shm")):
                raise ValueError("Restore requires a new database path with no WAL or SHM files")
            result = checked_backup(args.source, args.destination)
    else:
        result = checked_backup(args.source, args.destination)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
