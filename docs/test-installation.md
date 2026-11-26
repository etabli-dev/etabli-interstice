# Test runtime 0.1.0

This release is an isolated trial. It cannot publish calendar changes and must not replace a production scheduler. No production data or credentials are included.

## Build and start

Build the normal Dockerfile with a container engine:

```sh
docker build -t etabli-interstice:0.2.0-test .
```

On hosts where Docker build execution cannot inherit the required workload budget, use the tested image artifact from a successful CI run for the exact source revision. Verify its SHA256SUMS and OCI revision label before loading it. CI includes container startup, writer-lock, backup/restore and vulnerability checks, and exports the image plus its software inventory. The former dependency-overlay builder was removed because it retained base-image packaging tools and could not apply the required OS fixes.

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

The 0.3.0 candidate adds imported recurrence, retention of valid plan blocks and private snapshot migration. Workload-balancing optimization, active-timer reservations, calendar writes, subscription discovery UI, advanced task/series editing, notifications, mobile widgets and OIDC discovery remain pending. The Focus application is unchanged; the native adapter must be implemented and device-tested separately. MCP clients requiring OAuth enrollment rather than a configured bearer header are not supported yet.

The CalDAV polling connector requires an explicit collection URL. A separate read-only discovery helper supports credential-constrained principal/home/collection discovery. The browser does not yet expose discovery, and the connector does not implement sync tokens or ETag write-back. Live iCloud and Nextcloud interoperability remains unqualified until dedicated test-account checks. High-frequency recurrence and multiple intraday recurrence times are rejected to bound expansion. No calendar snapshot is assumed to be empty after a failed refresh.

Plans are calculated from current inputs when requested; flexible work can move between reads. There is no active-timer reservation yet. The planner does not guarantee optimal packing. Calculations have a 30-second wall deadline, five-second CPU budget and 256 MiB address-space limit in a disposable Linux worker. One worker runs at a time; excess calculations return a retryable 503. These limits preserve availability rather than guaranteeing every workload will fit. The 0.3.0 candidate bounds storage to 10,000 tasks including recurring occurrences; this is a guard, not a verified performance capacity claim. All credentials access only this test database; roles are instance-wide, not per list.

Browser progress buttons record individual test sessions. An operation is stored in a client-scoped browser outbox before sending; a lost response or reload preserves the same receipt. Web Locks serialize writes across tabs. Do not clear browser storage while an action is pending; local pending task text is not encrypted by the application. Focus's production session history must not be replayed against this instance. Do not use the browser button as an automatic time tracker.

## Model connection

Configure `INTERSTICE_MODEL_URL`, `INTERSTICE_MODEL`, and `INTERSTICE_MODEL_PROTOCOL`. For a private HTTP endpoint, explicitly set `INTERSTICE_ALLOW_PRIVATE_MODEL=1`; otherwise use HTTPS. For providers needing a key, mount a secret file and set `INTERSTICE_MODEL_KEY_FILE` in an override. Never enter provider keys into the browser.

Only the text entered into the draft form is sent to the provider, together with a task schema and current date/time-zone context. Existing calendars and tasks are not sent. The gateway has an overall 120-second deadline, one in-flight request and a 15-second minimum interval. The Ollama adapter disables thinking and requests at most 128 output tokens with two inference threads; budget these within the separate model service's CPU limit. It validates the returned task, has no tools or execution authority, and never silently falls back to a different provider. Slow-host latency is not production-qualified.

## Checks and recovery

```sh
python -m unittest discover -s tests -v
docker compose -f deploy/compose.test.yaml ps
docker compose -f deploy/compose.test.yaml logs --tail 50 app
```

Tests cover busy-time exclusion, splitting, shortage reporting, dependency cycles, fixed blocks, buffers, daylight-saving behavior, idempotency, progress replay, stale revisions, SQLite backup/restore, failed calendar snapshots, authentication, cookie origin checks and MCP role enforcement. A disabled model cannot mutate tasks.

Use SQLite's online backup API while running. Back up credentials separately with restricted access. Stop only the `interstice-test` Compose project to disable the trial; no other stack needs to be stopped. Do not use a global Docker prune or change existing scheduling integrations. Keep a backup before upgrading the test database.

External model availability, full device behavior, provider-specific calendar correctness and production readiness are separate acceptance checks. Passing these tests does not establish full functional parity.
