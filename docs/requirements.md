# Product requirements

Status: proposed, 2026-11-26. Every capability below is unimplemented in this repository.

## Product boundary

Interstice owns task scheduling and calendar projection. Focus owns the mobile interaction and focus timer. Project systems retain project structure. Calendar providers retain ordinary appointments. A task and its scheduled blocks are separate records: moving a block never silently changes its deadline.

The service must run independently of proprietary scheduling services. Standards-based connections are first-class. Personal installation comes first; a multi-tenant hosted service is outside the initial scope.

## Functional coverage

| Area | Required behavior |
| --- | --- |
| Planning | Automatic scheduling/replanning; explicit catch-up; eight-week horizon; stable plans |
| Constraints | Deadlines, priorities, earliest starts, dependencies, multiple hours profiles, exceptions |
| Capacity | Splittable work, minimum block size, travel/break buffers, balanced or front-loaded days |
| Overload | Visible unscheduled effort, lateness and reasons; no silent overlaps |
| Tasks | Inbox, lists, notes, fixed/flexible tasks, recurring occurrences, partial completion, history |
| Calendars | Local events, recurrence, all-day dates, busy/free, multiple calendars |
| Interface | Day, three-day, rolling-week, week and list views; deadline indicators; custom colors; dark mode |
| Mobile | Focus companion: tasks, schedule, progress, reminders, offline cache and widgets |
| Interoperability | CalDAV, iCloud, Nextcloud, ICS subscriptions; REST, MCP, webhook automation |
| Model connections | External MCP clients; configurable local-container or remote model API; scoped proposals and validated changes |
| Broader adapters | Google/Outlook calendars; Todoist, Google Tasks, Microsoft To Do; Apple Reminders import |

Public category benchmark: [FlowSavvy feature overview](https://flowsavvy.app/pricing), reviewed 2026-11-26. This table specifies independently implemented behavior; it does not claim current parity or prescribe a copied interface. Provider adapters outside CalDAV are later work, not silently omitted from the broader coverage target.

## Calendar requirements

1. Discover accessible CalDAV collections and explicitly select input calendars and one writable task calendar. Test iCloud and Nextcloud independently.
2. Accept HTTPS ICS subscriptions, normalizing webcal links to HTTPS where supported. A subscription is read-only; it cannot receive task changes.
3. Allow per-calendar busy/free interpretation, including holiday and all-day feeds. Preserve IANA time zones, recurrence exceptions, cancelled instances and date-only values.
4. Never automatically move ordinary appointments, send invitations or modify attendee-bearing events. Interactive event editing remains separate from scheduling and initially supports own events without attendees.
5. Calendar deletion, task completion and task deletion are distinct actions. A disappeared projection does not complete a task.
6. Stale feeds remain visibly stale. A failed refresh never means that every event disappeared. Suspend publication when required availability is too stale.

## Scheduling semantics

Estimate minus credited progress determines remaining work. Progress cannot become negative or accidentally count the same focus session twice. Completed and currently active blocks are stable. Pinned blocks remain fixed; conflicts appear explicitly.

Recurrence creates stable occurrence IDs, each with its own eligibility window, deadline and progress. Editing one occurrence differs from changing the series. Initially reject dependencies involving recurring series unless explicit occurrence mapping is provided; reject all dependency cycles.

Deadlines are a target whose violation must be reported. Busy time, valid hours, earliest start, dependency order and locked commitments are hard constraints. If work cannot fit, return a partial plan with quantified shortage rather than a fictitious feasible plan.

## Acceptance examples

- A moved appointment displaces only affected flexible work; an active Focus timer remains unchanged.
- A two-hour task with 30-minute minimum blocks can fit in two one-hour gaps; 20-minute gaps do not qualify.
- Crediting 25 minutes twice with the same session identifier credits exactly 25 minutes.
- In a day with two free hours and four hours of due work, show two hours of shortage.
- Europe/Berlin spring and autumn clock changes preserve intended local recurrence and never duplicate an occurrence.
- A disconnected phone shows cached schedule freshness and queues progress; reconnecting does not duplicate it.
- CalDAV precondition failure produces reconciliation, not a blind overwrite of an external edit.
- One stale subscription cannot erase commitments or cause a burst of conflicting calendar writes.
