# Delivery and replacement gates

All milestones are pending. This repository is a specification, not a finished replacement.

| Stage | Deliverable | Exit evidence |
| --- | --- | --- |
| 0 | Requirements, independent branding, license, generic architecture | Reviewed concept; private deployment mapping kept separately |
| 1 | Domain model, API, single-container persistence | Task/progress contracts, revision and idempotency tests, restore drill |
| 2 | CalDAV and subscription inputs | iCloud + Nextcloud live sandbox tests; recurrence/DST/failure fixtures |
| 3 | Scheduler and calendar projection | Constraint invariants, overload reporting, stable replans, uncertain-write recovery |
| 4 | Focus companion adapter and views | iOS/Android device acceptance, offline receipts, explicit completion, reminders |
| 5 | Project and follow-up adapters | Existing caller contract tests, preserved mappings, duplicate prevention |
| 6 | Shadow operation and cutover | 7–14 days of comparison, reconciled export, one writer, rollback rehearsal |
| 7 | Broader ecosystem and full coverage | Additional providers, task adapters, mobile widgets and all remaining requirements verified |

Stages 4 and 5 can be developed against the API contract once stage 1 stabilizes. Do not claim full category parity at stage 6 if stage 7 features are still missing. For a personal replacement, the owner may explicitly decide that unused integrations are unnecessary; that does not turn them into implemented features.

## Replacement gate

Required before retiring the old service: preserved task data and history; verified iCloud/Nextcloud/subscription behavior; acceptable scheduling and visible overload; reliable Focus progress/completion; functioning project/follow-up flows; private credential handling; tested backup/restore and rollback; no double scheduling writer.

## Quality gates

Use property-based scheduler tests for non-overlap, bounds and conserved remaining effort. Use synthetic calendar fixtures for recurrence exceptions, ambiguous time zones and large feeds. Inject timeouts before and after provider writes, token invalidation, ETag conflicts, duplicate webhooks and interrupted database transactions.

Mobile acceptance must include app suspension, denied notification permissions, offline work, device restore and retries. Measure actual latency and resource usage on the intended host before enabling background publication.
