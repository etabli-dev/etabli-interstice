# Établi Interstice

Make room for the work that matters.

Établi Interstice is a proposed self-hosted scheduling service: it places tasks around calendar commitments, adapts when plans change, and explains when there is too much work for the time available. **Établi Focus is its mobile companion**, connecting to the service for tasks, schedules, focus progress and completion. A browser interface provides planning and administration.

**Status: concept and implementation specification. There is no runnable application, published container image or verified feature implementation yet.**

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
| [Licensing and independence](docs/legal.md) | Rights, provenance and unresolved clearance |

No production calendar or task system should be switched to this project at the concept stage. All capabilities above are planned, not advertised as working.

## Licensing

AGPL-3.0-only provides strong copyleft, including obligations for covered modified versions offered over a network. Commercial use, modification and redistribution remain permitted under the license. There is no noncommercial clause or additional use restriction. See [LICENSE](LICENSE), [NOTICE](NOTICE), [trademark policy](TRADEMARKS.md) and [contribution policy](CONTRIBUTING.md).

This project is independent of calendar and task service providers. Provider names in integration and migration documentation identify interoperability targets, not affiliation or endorsement.
