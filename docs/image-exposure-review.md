# Container exposure review — 26 November 2026

The scanned candidate has no fixable high or critical findings at scan time. This is not a zero-vulnerability claim. The full report and CycloneDX inventory accompany each CI image artifact; do not replace them with this summary. Package updates and changed application paths require another review.

The preceding hardened image contained 53 high package findings representing 13 unique, currently unfixed CVEs. The following exposure assessment is an inference from the Debian tracker descriptions and the current container configuration, not an exploit test or an upstream fix.

| Finding | Required path and present constraint |
| --- | --- |
| [CVE-2026-76642](https://security-tracker.debian.org/tracker/CVE-2026-76642), [CVE-2026-78408](https://security-tracker.debian.org/tracker/CVE-2026-78408), [CVE-2026-78409](https://security-tracker.debian.org/tracker/CVE-2026-78409), [CVE-2026-78410](https://security-tracker.debian.org/tracker/CVE-2026-78410) | Privileged mount or namespace tooling. The service runs without root, capabilities or privilege escalation and does not execute these tools. |
| [CVE-2026-54369](https://security-tracker.debian.org/tracker/CVE-2026-54369) | Privileged pathname ACL operations. The application performs no such operations. |
| [CVE-2025-69720](https://security-tracker.debian.org/tracker/CVE-2025-69720) | The infocmp command. The application does not invoke terminal tools. |
| [CVE-2026-119373](https://security-tracker.debian.org/tracker/CVE-2026-119373), [CVE-2026-119374](https://security-tracker.debian.org/tracker/CVE-2026-119374), [CVE-2026-119379](https://security-tracker.debian.org/tracker/CVE-2026-119379) | SQLite FTS5 or session changesets. The schema uses ordinary tables and parameterized queries; no FTS5, changeset ingestion, arbitrary SQL or database upload endpoint. Restore must use trusted backups. |
| [CVE-2026-107494](https://security-tracker.debian.org/tracker/CVE-2026-107494), [CVE-2026-124709](https://security-tracker.debian.org/tracker/CVE-2026-124709) | OpenSSL QUIC paths. The service uses HTTP over TCP and no QUIC/HTTP3. |
| [CVE-2026-16742](https://security-tracker.debian.org/tracker/CVE-2026-16742) | systemd-homed account management. No homed service runs in the container. |
| [CVE-2026-9538](https://security-tracker.debian.org/tracker/CVE-2026-9538) | Perl Archive::Tar input processing. The application accepts no archive uploads and invokes no Perl archive tooling. |

These findings remain visible, with no suppression file. Adding shell hooks, privileged execution, arbitrary database restore, FTS search or HTTP3 invalidates the corresponding assessment. Medium, low and unknown findings are not fully triaged here. Signed release provenance and an independent penetration test remain separate release work.
