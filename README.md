# Établi Interstice

Make room for the work that matters.

Établi Interstice is a self-hosted scheduling service under development: it places tasks around calendar commitments and explains when there is too much work for the time available. **Établi Focus is the designated mobile companion**; its Interstice adapter is still pending. A browser interface provides the current test workspace.

**Status: hardened 0.2.0 test container, not a production replacement.** The initial runtime supports tasks, deterministic schedule previews, deadlines, dependencies, splitting, fixed blocks, progress receipts, CalDAV/ICS reads, authenticated MCP and an optional external model connection. External calendar writes are absent by design. Recurring tasks, mobile integration, stable persisted plans, project migration and broader provider adapters remain pending. No public registry image is published yet; build from source.

Part of the [Établi Suite](https://github.com/etabli-dev). Licensed under **AGPL-3.0-only**. The working name refers to the spaces between commitments; it is not a claim of registered trademark protection.

## Intended experience

- Connect iCloud, Nextcloud and other CalDAV calendars; subscribe to read-only webcal/ICS feeds.
- Enter tasks with effort, deadline, priority, dependencies and suitable working hours.
- Review an eight-week plan, keep fixed appointments intact and recalculate unfinished work.
- Open [Établi Focus](https://github.com/etabli-dev/etabli-focus) on your phone to see what is next, start focused work and report progress.
- Retain your project manager and automation tools through versioned APIs and an optional MCP adapter.
- Connect an external model client over MCP, or configure a model API in another container or at a remote provider for natural-language planning.
- Run one application container with persistent storage, behind your existing HTTPS proxy.

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

The intended experience above remains the target; only the explicitly listed test-runtime features are implemented. Do not switch a production calendar or task system to this release.

## Licensing

AGPL-3.0-only provides strong copyleft, including obligations for covered modified versions offered over a network. Commercial use, modification and redistribution remain permitted under the license. There is no noncommercial clause or additional use restriction. See [LICENSE](LICENSE), [NOTICE](NOTICE), [trademark policy](TRADEMARKS.md) and [contribution policy](CONTRIBUTING.md).

This project is independent of calendar and task service providers. Provider names in integration and migration documentation identify interoperability targets, not affiliation or endorsement.
