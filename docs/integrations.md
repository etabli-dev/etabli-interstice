# Integrations and migration

## Établi Focus is the companion

The existing [Établi Focus](https://github.com/etabli-dev/etabli-focus) application becomes the mobile client. Do not create a second mobile application. Replace its current scheduling-provider adapter with an Interstice implementation of a provider-neutral interface:

`connect`, `capabilities`, `listTasks`, `getSchedule`, `recordProgress`, `completeTask`, `operationStatus`.

The server owns tasks and plans; Focus owns timers and local session history. Focus sends productive time only, excluding breaks and pauses. Preserve explicit confirmation for completion. Task completion must not be inferred from a timer ending.

Focus stores credentials using platform-protected storage, caches the upcoming week, displays last-sync time and queues receipts durably. Each installation has a random identifier; each focus session has a UUID. Retrying or restoring a phone must not replay already-credited progress. Offline writes carry original task revisions; conflicts require reconciliation.

Add a schedule view and next-task action alongside the timer. Mobile notifications, background refresh and widgets belong in Focus. Device tests must verify delivery and stale-cache behavior; a browser installation does not constitute native-widget parity. Existing desktop Focus clients may use the same API, with platform-appropriate credential storage.

Authenticate mobile clients using authorization code with PKCE through an optional OIDC provider, with no client secret embedded in the app. A standalone installation may use individually revocable scoped device credentials until OIDC is configured. Do not reuse a server administrator token on phones.

## Calendar priorities

| Connector | Initial scope | Write destination |
| --- | --- | --- |
| iCloud CalDAV | Read selected calendars, expand recurrence, publish task blocks | Dedicated iCloud task calendar |
| Nextcloud CalDAV | Same; server discovery and per-collection permissions | Dedicated Nextcloud task calendar |
| Other CalDAV servers | Capability probing and conformance tests | Explicitly selected writable collection |
| webcal / HTTPS ICS | Conditional fetch, recurrence, freshness and subscription controls | None: read-only |

An app-specific password is a supported route for third-party iCloud access; revocation and account password changes require reconnection. Never request the primary account password. See [Apple authentication guidance](https://support.apple.com/en-us/102654) and [Nextcloud user documentation](https://docs.nextcloud.com/server/latest/user_manual/en/groupware/calendar_basics.html).

Subscriptions are arbitrary URLs: restrict schemes, enforce TLS, bound response sizes and expansion, validate redirects and resolved addresses. Block metadata endpoints and unexpected private networks. Explicit administrator-approved internal Nextcloud hosts are an exception, not a general private-network bypass. Treat token-bearing feed URLs as credentials and redact them from logs.

Later provider adapters cover Google and Outlook calendars and external task systems. Apple Reminders import requires a separately verified supported device-side mechanism; do not assume iCloud CalDAV exposes modern Reminders. Optional Nextcloud VTODO integration is separate from calendar VEVENT projection.

## Projects and automation

Keep project structure and governance in the project manager. Schedule only actionable, selected work. Maintain a field-ownership matrix: project deadlines/dependencies, scheduler effort/planned blocks, shared title/priority with three-way comparison and visible conflicts. Replanning must not rewrite project start/due dates.

An on-hold project task becomes unscheduled. Removing assignment moves it out of scheduling scope without deletion. Closing or reopening a linked task uses explicit synchronization rules. Never bulk-import historical documentation as actionable work.

Preserve existing external task-tool contracts through an adapter rather than forcing every producer to change simultaneously. Keep source markers, duplicate checks across open and completed tasks, durable mutation receipts, and uncertain-write reconciliation. The migration must cover mail/document follow-ups, project sync, Focus and scheduled automation—not only the browser.

## Cutover

1. Inventory all writers and readers, current permissions and exact external contracts. Export authorized task data, lists, recurrence, progress, dependencies and mappings through documented interfaces; verify pagination and report unavailable fields.
2. Import into an isolated database. Retain original IDs and provenance. Reconcile counts and representative records, including completed and recurring work. A calendar-only export is insufficient to reconstruct task semantics.
3. Run a read-only shadow planner for 7–14 days. Exclude old scheduler projections from busy-time inputs using verified ownership/mappings; leave real appointments intact. Publish nothing.
4. Test Focus, project sync and follow-ups against a disposable list/calendar. Verify duplicate protection, time zones and recovery from provider failures.
5. Pause old task/calendar writers, take a final delta export, reconcile state and switch adapters together. Use one active scheduling writer. Archive old projections without touching ordinary events.
6. Enable the dedicated output calendar and verify mobile delivery, task completion and project updates. Keep a versioned cutover ledger and retained legacy export.
7. Cancel the former service only after acceptance. On rollback, pause new writers, reconcile changes since cutover into the former system, retire only owned new projections and then resume the old writer. A database restore alone is not a safe rollback.

Product feature parity does not require identical event placement. Compare constraints, task preservation and usability, not proprietary algorithm behavior.
