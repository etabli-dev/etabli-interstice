# Production acceptance record

**Decision: production replacement is not approved.** This is a hardened test candidate. Passing software checks does not complete provider, device, migration or sustained-operation acceptance.

## Implemented safeguards

- One application process holds an exclusive filesystem lease before startup. The container entry point permits one writer and eight concurrent HTTP connections; SQLite remains local, with WAL and durable operation receipts.
- Browser mutations persist before network access. A lost response, reload or expired login preserves the receipt; Web Locks coordinate tabs. Definitive validation errors can be corrected. Pending browser data must not be cleared during recovery.
- Calendar parsing and scheduling execute in disposable Linux subprocesses, with one calculation slot, 256 MiB address-space limit, a bounded trusted-import phase followed by five CPU seconds (six-second hard limit) for input processing, and a 30-second wall deadline. A failed or busy calculation yields retryable failure rather than silently emptying calendars.
- An independent validator checks effort conservation, deadlines, working windows, dependencies, fixed blocks, busy time, buffers and overlap before plan acceptance. Input changes during computation reject the candidate. Preview snapshots survive process restart; this is not a full incremental planner.
- Source freshness is explicit. A disconnected source is removed; a new source starts unready; refresh failures retain prior snapshots. Sources older than 15 minutes show stale status. Calendar publication is absent.
- HTTPS is required for non-loopback public origins. Request bodies have byte and time bounds. Session exhaustion does not log out unrelated clients. Storage failures return retryable responses.
- The image remains non-root, with a read-only root filesystem, dropped capabilities, resource budgets and bounded logs. The server uses a private umask. Model calls have no task-writing authority.
- Read-only CalDAV discovery checks every destination before forwarding credentials. Only explicit HTTPS hosts are allowed; the iCloud policy can explicitly allow Apple-controlled subdomains. Redirect tests verify that credentials never reach an unauthorized host.

## Recovery commands

Use the container entry point for the server; bypassing it bypasses the exclusive writer lease. Filesystem locking is not a distributed lock and does not make network storage safe.

```sh
python -m app.manage backup /data/interstice.sqlite /data/backups/unique-backup.sqlite
python -m app.manage restore /data/backups/unique-backup.sqlite /new-empty-data/interstice.sqlite
```

Backup uses SQLite's online backup API, checks integrity, creates a private file, flushes it and publishes it without overwriting another backup. Restore requires a new destination, no existing WAL/SHM files, and exclusive access. Stop the application before restoring the deployment. Back up credentials separately with equivalent protection. Rehearse restoration and client receipt lookup before any cutover.

The 0.2.0 database change adds a preview cache only. Keep the pre-upgrade backup and old image. An old binary may ignore the added table; preserve receipt data and never replay old timer history as new work.

## Evidence and open gates

| Gate | Current evidence or remaining requirement |
| --- | --- |
| Core invariants and failure recovery | Automated scheduling, concurrent receipts, worker failure, cache invalidation, backup and API tests; 80 deterministic randomized scheduling cases |
| Browser ambiguous writes | Real headless browser: accepted progress response dropped, reload, retry; exactly 25 minutes credited once; no script errors or mobile overflow |
| Dependency audit | Pinned Python packages checked with pip-audit; no known vulnerabilities returned at audit time. Full-image scanning also runs in CI, with an exported software inventory and a failing gate for fixable high/critical findings. Unfixed OS findings still require exposure review; no zero-vulnerability claim is made. Signed release provenance remains separate work |
| iCloud | Live read-only discovery and event-fetch qualification passed; account details and counts remain in private evidence |
| Nextcloud | Live read-only discovery and event fetch passed using the supplied account app password. No password reset or calendar mutation performed |
| Model service | Live latency remains unqualified; shared-host resource pressure is unresolved. Core scheduling must work without inference |
| Scheduling feature completeness | Task recurrence, stable incremental replans, active timer reservations and richer availability remain unfinished |
| Focus | Native adapter and iOS/Android/desktop offline/device acceptance remain unfinished |
| Migration | Existing project/follow-up consumers, exports and single-writer cutover are not migrated |
| Sustained operation | Restore rehearsal on deployment, capacity measurements under representative load, monitoring/backup ownership, and a 7–14 day shadow run required |

Do not change the production provider, enable a second calendar writer, or describe this release as a complete replacement until the remaining gates have evidence. Authentication is intended for a personal instance with scoped bearer clients; OAuth enrollment and multi-user tenant isolation are not implemented.
