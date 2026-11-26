# Test runtime 0.1.0

This release is an isolated trial. It cannot publish calendar changes and must not replace a production scheduler. No production data or credentials are included.

## Build and start

Build the normal Dockerfile with a container engine:

```sh
docker build -t etabli-interstice:0.1.0-test .
```

On hosts that enforce workload limits outside the Docker build daemon, run `scripts/build-prepared.sh` through the host's workload wrapper. Set `TMPDIR` to a private temporary directory and `INTERSTICE_PYTHON` to Python 3.13. The script requires `uv`, installs only hash-verified binary wheels into temporary staging and builds an image without executing dependency installation in Docker. The prepared build currently targets the build host's Linux architecture; cross-architecture output is not qualified.

Create `deploy/data` owned by UID/GID 10005 and a private `deploy/secrets/tokens.json` readable by UID 10005. Its schema is a JSON array containing `id`, `role` (`admin` or `read`) and an independently generated random `token` of at least 32 characters per client. Generate tokens with a cryptographic random generator; do not copy example credentials or store the file in Git.

```sh
docker compose -f deploy/compose.test.yaml up -d
```

Open `http://localhost:8095/` and sign in with the owner test key. The default port binds only to loopback. For a remote deployment, put it behind HTTPS and configure `INTERSTICE_PUBLIC_URL` including any path prefix. The reverse proxy must strip that prefix; provide the trailing slash in the launch URL. Cookies are secure on HTTPS and scoped to that path.

The Compose stack contains the application and a separate read-only synthetic CalDAV fixture. The fixture is not a general CalDAV server and is never publicly routed. It also exposes an ICS feed for testing. No iCloud or Nextcloud account is connected by default.

## Current coverage

- Browser task creation, seven-day agenda, eight-week planning preview, completion and productive-minute credit.
- Task API with revisions, durable idempotency receipts and cumulative per-session progress. Tokens represent stable client IDs; keep a device's client ID stable when rotating its credential.
- First-fit scheduling with deadlines, earliest start, priorities, working-day/hour profiles, splitting, minimum block sizes, buffers and acyclic dependencies.
- Fixed blocks are reserved before flexible work; conflicts are reported. Fixed blocks with dependencies are explicitly rejected.
- Read-only CalDAV REPORT against an explicit collection URL and ICS fetches; recurrence expansion with time-zone handling. Poll every five minutes or refresh manually. Failed reads retain the prior snapshot and show an error.
- MCP over Streamable HTTP with pinned SDK, bearer authentication and admin/read roles. Supported tools: `tasks_list`, `schedule_get`, `task_create`, `task_progress`, `task_complete`, `operation_get`.
- Optional proposal-only model gateway. `ollama` calls `/api/chat`; `chat-completions` calls `/chat/completions` below the configured base URL. A model fills a task draft; the user explicitly creates it.

## Known limits

No task recurrence, persisted stable plans, workload-balancing optimization, calendar writes, subscription discovery UI, advanced task editor, notifications, mobile widgets, OIDC discovery or project migration. The Focus application is unchanged; the native adapter must be implemented and device-tested separately. MCP clients requiring OAuth enrollment rather than a configured bearer header are not supported yet.

The CalDAV connector requires an explicit collection URL. It does not implement account discovery, sync tokens or ETag write-back. Live iCloud and Nextcloud interoperability remains unqualified until dedicated test-account checks. High-frequency recurrence and multiple intraday recurrence times are rejected to bound expansion. No calendar snapshot is assumed to be empty after a failed refresh.

Plans are calculated from current inputs when requested; flexible work can move between reads. There is no active-timer reservation yet. The planner does not guarantee optimal packing or a wall-clock calculation deadline. API access is bounded to 1,000 tasks; this is a guard, not a verified performance capacity claim. All credentials access only this test database; roles are instance-wide, not per list.

Browser progress buttons record individual test sessions. Focus's production session history must not be replayed against this instance. Do not use the browser button as an automatic time tracker.

## Model connection

Configure `INTERSTICE_MODEL_URL`, `INTERSTICE_MODEL`, and `INTERSTICE_MODEL_PROTOCOL`. For a private HTTP endpoint, explicitly set `INTERSTICE_ALLOW_PRIVATE_MODEL=1`; otherwise use HTTPS. For providers needing a key, mount a secret file and set `INTERSTICE_MODEL_KEY_FILE` in an override. Never enter provider keys into the browser.

Only the text entered into the draft form is sent to the provider, together with a task schema and current date/time-zone context. Existing calendars and tasks are not sent. The gateway has a 120-second timeout, one in-flight request and a 15-second minimum interval. The Ollama adapter disables thinking and requests at most 256 output tokens on one thread. It validates the returned task, has no tools or execution authority, and never silently falls back to a different provider. Slow-host latency is not production-qualified.

## Checks and recovery

```sh
python -m unittest discover -s tests -v
docker compose -f deploy/compose.test.yaml ps
docker compose -f deploy/compose.test.yaml logs --tail 50 app
```

Tests cover busy-time exclusion, splitting, shortage reporting, dependency cycles, fixed blocks, buffers, daylight-saving behavior, idempotency, progress replay, stale revisions, SQLite backup/restore, failed calendar snapshots, authentication, cookie origin checks and MCP role enforcement. A disabled model cannot mutate tasks.

Use SQLite's online backup API while running. Back up credentials separately with restricted access. Stop only the `interstice-test` Compose project to disable the trial; no other stack needs to be stopped. Do not use a global Docker prune or change existing scheduling integrations. Keep a backup before upgrading the test database.

External model availability, full device behavior, provider-specific calendar correctness and production readiness are separate acceptance checks. Passing these tests does not establish full functional parity.
