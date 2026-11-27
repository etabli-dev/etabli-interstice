# Établi Interstice

Make room for the work that matters.

Établi Interstice is a self-hosted scheduling service under development: it places tasks around calendar commitments and explains when there is too much work for the time available. **Établi Focus is the designated mobile companion**; its candidate Interstice adapter supports desktop, Android and iOS. A browser interface provides the current test workspace.

**Status: 0.3.0 migration runtime with authenticated production task writes.** The runtime supports tasks, deterministic schedule previews, deadlines, dependencies, splitting, fixed blocks, progress receipts, CalDAV/ICS reads, authenticated MCP and an optional external model connection. External calendar writes are absent by design. Private snapshot import, recurring task materialization, availability profiles, overdue reporting and retention of valid plan blocks are implemented. Local compatibility routes preserve imported task IDs and support existing consumers without provider fallback. Structural recurrence editing and active-timer reservations remain unavailable; physical-device Focus acceptance and sustained-operation checks remain deployment-specific. See [migration and shadow operation](docs/migration.md) and the [compatibility contract](docs/compatibility.md). No public registry image is published yet; build from source.

Part of the [Établi Suite](https://github.com/etabli-dev). Licensed under **AGPL-3.0-only**. The working name refers to the spaces between commitments; it is not a claim of registered trademark protection.

## Intended experience

- Connect iCloud, Nextcloud and other CalDAV calendars; subscribe to read-only webcal/ICS feeds.
- Enter tasks with effort, deadline, priority, dependencies and suitable working hours.
- Review an eight-week plan, keep fixed appointments intact and recalculate unfinished work.
- Open [Établi Focus](https://github.com/etabli-dev/etabli-focus) on your phone to see what is next, start focused work and report progress.
- Retain your project manager and automation tools through versioned APIs and an optional MCP adapter.
- Connect an external model client over MCP, or configure a model API in another container or at a remote provider for natural-language planning.
- Run one application container with persistent storage, behind your existing HTTPS proxy.

See [task organization](docs/task-organization.md) for the nine action categories, optional discussion details, and explicit list consolidation.
New tasks receive [automatic metadata suggestions](docs/classification.md), including privately configured project contacts. Explicit edits take precedence over suggestions.

## Design documents

| Document | Purpose |
| --- | --- |
| [Product requirements](docs/requirements.md) | Functional scope and acceptance criteria |
| [Architecture](docs/architecture.md) | Scheduling, data model, sync and API |
| [Integrations and migration](docs/integrations.md) | Focus companion, calendars, projects and cutover |
| [Model connections](docs/model-connections.md) | MCP tools, external model containers and provider APIs |
| [Container operations](docs/deployment.md) | Packaging, isolation, budgets and recovery |
| [Delivery plan](docs/roadmap.md) | Ordered milestones and replacement gates |
| [Production acceptance](docs/production-readiness.md) | Hardening evidence and outstanding cutover gates |
| [Runtime audit](docs/audit-2026-11-26.md) | Findings, regression evidence and remaining gates |
| [Test installation](docs/test-installation.md) | Build, credentials, testing and operational limits |
| [Licensing and independence](docs/legal.md) | Rights, provenance and unresolved clearance |

The intended experience above remains the target; only the explicitly listed runtime features are implemented. A task-store cutover requires a reconciled final export, drained source writers, consumer contract checks and recovery verification. Production mode is not a claim of complete provider feature parity.

## Licensing

AGPL-3.0-only provides strong copyleft, including obligations for covered modified versions offered over a network. Commercial use, modification and redistribution remain permitted under the license. There is no noncommercial clause or additional use restriction. See [LICENSE](LICENSE), [NOTICE](NOTICE), [trademark policy](TRADEMARKS.md) and [contribution policy](CONTRIBUTING.md).

This project is independent of calendar and task service providers. Provider names in integration and migration documentation identify interoperability targets, not affiliation or endorsement.
