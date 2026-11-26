# Container and operations concept

No image or executable Compose configuration is provided yet. These are implementation requirements, not deployment instructions for a working service.

## Packaging

Ship one OCI application image with the API, compiled web UI and bounded background workers. Support amd64 and arm64 after both are tested. Default to one replica and SQLite WAL on a local persistent volume. Use existing HTTPS ingress and optional OIDC; neither a particular proxy nor a particular identity vendor is mandatory.

Run as an unprivileged UID, read-only root filesystem, writable data volume and bounded tmpfs. Drop capabilities, set no-new-privileges, bound PIDs, and never mount the Docker socket. The service needs no host networking or privileged mode. Restrict exposed traffic to HTTPS ingress; database files are never served.

Initial sizing hypothesis: 0.5 CPU, 512 MiB RAM, one scheduling worker, bounded 5-second scheduling attempts. Benchmark approximately 1,000 active tasks and eight weeks of calendar occurrences; raise limits only with measured justification. These numbers are not established capacity or latency claims. Set numerical library threads to one.

## Configuration and secrets

Configuration includes public origin, IANA time zone, data path, authentication settings, read freshness limits, calendar polling policy, publication mode and optional provider adapters. Default publication mode is shadow/read-only. Real calendars and provider credentials must never be baked into an image or example configuration.

Use mounted secret files or a secret manager. Encrypt stored provider credentials with a separately backed-up key. Restrict task/calendar access per client and calendar; revoke devices independently. Source code availability does not make private account data public.

Expose liveness independently from calendar-provider availability. Readiness checks database health and migrations; provider failures appear as degraded integration status. Record queue depth, last successful sync, oldest uncertain operation, scheduler duration, deadline shortage, memory and backup age without task titles.

## Backup and recovery

Use SQLite online backup or a coordinated checkpoint/snapshot, not an uncoordinated copy of the main file while WAL is active. Encrypt off-host backups and retain the credential key separately. Test restoration in an isolated installation with publication disabled.

Proposed objectives: daily full backup, hourly database recovery point and two-hour recovery time for a personal installation. These remain unverified until restore drills demonstrate them. Recover uncertain operations by reading providers before replaying any writes.

Version migrations; back up before upgrades. Pin release images by digest. Provide rollback compatibility notes rather than assuming an old executable can read a newly migrated database.

## Release artifacts

Publish versioned source, Dockerfile, lockfiles, build instructions, source revision labels, SBOM, license notices and corresponding source alongside every image. The running UI exposes its exact version and source link. Include downstream changes in source offers for covered modified versions; a link to an unmodified upstream tree is insufficient.

Before release, verify dependency licenses, image vulnerabilities, architecture builds, unprivileged execution, restore behavior, mobile compatibility and a complete source build. No runtime dependency or base-image license audit has happened at the concept stage.
