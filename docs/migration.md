# Private migration and shadow operation

The 0.3.0 candidate accepts a complete read-only FlowSavvy MCP export. It is not
approved for production cutover. Store exports, databases, credentials, real
calendar mappings and operational evidence outside this public repository.

An export has format `flowsavvy-mcp-export-v1`, `finished_at`, responses from
`list_lists`, `list_calendars`, `list_scheduling_hours`, and four `collections`:
task/event crossed with completed false/true. Each collection contains `pages`
from `list_items`, following every `nextPageToken` until exhausted. Do not filter
by list: inbox and archived completion history must remain in scope. Capture the
source schedule separately for comparison. Reject repeated page tokens, partial
reads and conflicting versions of one item. The source remains editable, so a
snapshot is not a transactional freeze; reconcile another export during cutover.

The public provider contract is the [official API specification](https://my.flowsavvy.app/api/docs/public/openapi.json).

```sh
python -m app.migration /private/export.json --database /private/new-shadow/interstice.sqlite --zone Europe/Berlin
```

Import refuses an existing database and validates all task mappings first.
The SQLite archive retains the exact original export and each original task/event
document, including notes, colors, IDs, timestamps and provider metadata. Native
task IDs use the `flowsavvy:` prefix. Cumulative progress gets one migration receipt;
old Focus session history must never be replayed as new progress. Events are archived
but are not automatically made calendar inputs: qualify their source mappings first.

Imported task execution preserves priority, list, completion, effort, progress,
dependencies, fixed intervals, buffers, availability windows and date overrides.
Floating times use the explicitly selected account zone. Ambiguous/nonexistent
wall times, asymmetric buffers, edited recurrence exceptions, missing dependency
targets and unsupported rules stop import rather than silently changing meaning.
Raw archived metadata is not a claim that every field has a native editor.

Recurring templates reside in `series`; generated tasks have deterministic
occurrence IDs and separate durable progress/completion. Reads materialize the
rolling 56-day horizon, never replacing an existing occurrence. Cancelled dates
are excluded. Daily, weekly, monthly and yearly date-based RRULEs are supported;
subdaily rules and series dependencies are rejected. Imported series can be
inspected with `GET /api/v1/series`; a native series editor remains pending.
Historical source records remain in the archive. The total task guard is 10,000,
including retained occurrences; this is a bound, not a capacity certification.

Set `INTERSTICE_MODE=shadow` to deny task changes even for an admin credential.
The source system remains authoritative. Shadow mode still updates local calendar
snapshots, generated occurrences and plan caches; it never writes to calendars or
the source task provider. Do not attach a production task writer to a shadow instance.

Before cutover, verify field-level reconciliation, calendar coverage, active timer
behavior, Focus devices, existing follow-up/project consumers, deployment recovery,
representative capacity and 7–14 days of observation. Re-export and reconcile the
source while its writers are drained; preserve the pre-cutover database, source
export and tested image. Choose one authoritative task writer. Do not cancel the
old subscription or delete its data as part of a technical deployment.
