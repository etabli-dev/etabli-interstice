# External model connections

Status: initial test subset implemented. The runtime offers authenticated MCP task/schedule/progress tools and proposal-only Ollama or chat-completions API connections. Fine-grained per-list scopes, OIDC authorization, automatic model tool loops and the broader tool surface below remain targets. Neither mode requires embedding a model or model weights in its application container.

## 1. External client uses Interstice through MCP

Expose `/mcp` using the supported HTTP transport of a pinned MCP SDK and explicitly negotiated protocol revisions. An external application or service runs the model and an MCP client; that client discovers and calls Interstice tools. A bare inference endpoint does not automatically become an MCP client.

Initial tool surface:

| Tool group | Proposed tools | Permission |
| --- | --- | --- |
| Inspect | `tasks_list`, `task_get`, `schedule_get`, `availability_get` | Selected lists/calendars, bounded dates and pagination |
| Propose | `task_propose`, `plan_preview`, `plan_explain` | No persistent task or calendar mutation |
| Change | `task_create`, `task_update`, `task_progress`, `task_complete`, `plan_recalculate` | Explicitly granted write scopes and owner policy |
| Reconcile | `operation_get` | Caller-owned operation receipts |

Tool names are a proposed native contract; existing callers receive a separately tested compatibility adapter. All tools share the REST API's authorization, revisions, idempotency, rate limits, audit trail and durable outbox. Authentication is required even on private networks. Support individual service credentials for container clients and standards-compliant MCP authorization for interactive remote clients; browser cookies alone are insufficient for arbitrary MCP clients.

Default grants are read/propose. The owner may grant bounded automatic task writes to trusted integrations; this does not require repeated interactive approval for every already-authorized operation. Unapproved actions return a proposal for Focus or the browser. No tool exposes a shell, database access, provider credentials or unrestricted network requests.

## 2. Interstice calls an external inference API

For natural-language entry in Focus or the web planner, provide an optional model gateway. It calls an administrator-configured endpoint in another container, on a separate server, or at a hosted provider. Start with a documented HTTP inference adapter and add provider-native adapters as needed. Verify each provider's structured-output and tool-call capabilities; do not assume that nominal API compatibility guarantees them.

Flow: user request → permitted context selection → model → schema-validated proposal → policy decision → domain API → deterministic scheduler → result. Examples include turning “prepare the report for Friday, about two hours” into a task proposal, suggesting a breakdown or explaining a plan. Resolve missing or ambiguous deadlines visibly; model suggestions are not evidence of commitments.

Focus sends natural-language requests to Interstice, not directly to the model provider, so server-side policy and credentials stay centralized. The Focus timer, normal task editing and automatic scheduling remain available without model access.

A model may request only registered, scoped domain tools. Bound tool rounds and validate every argument; tool output cannot grant new permissions. Never execute generated code. Persist operation identifiers before any mutation and reconcile interrupted tool calls before retrying.

MCP exposes application tools; an inference API supplies model output. They are complementary interfaces, not interchangeable protocols. Do not depend on MCP sampling for the core gateway: current SDK documentation marks sampling deprecated and recommends direct provider API integration. Recheck protocol support at implementation time. See [MCP Python SDK guidance](https://py.sdk.modelcontextprotocol.io/handlers/sampling-and-roots/) and [MCP SDK overview](https://java.sdk.modelcontextprotocol.io/).

## Data and operation boundaries

- Send only context allowed for the authenticated caller and configured provider. Default to selected task fields and free/busy intervals; calendar descriptions and source documents require separate scope.
- Treat task notes, event descriptions and tool results as untrusted data, never as instructions that change policy or reveal secrets.
- Keep model keys server-side, mounted from secret files; redact credentials and token-bearing URLs from diagnostics. Do not retain full prompts by default.
- Permit only configured inference hosts; validate redirects and prevent access to unrelated internal services. Credentials are bound to their provider and are never forwarded to MCP callers.
- Set request timeouts, maximum context/output sizes, concurrency and usage budgets. Report usage and failures without logging private task content.
- A local provider outage cannot trigger remote disclosure through an automatic fallback. A timeout or invalid response leaves a proposal failed and never fabricates a successful mutation.
- Maintain a visible preview with changed fields, provenance, relevant input revisions and expiry. Approval is invalidated by material changes to the proposal or underlying task.

## Acceptance evidence

Connect one external MCP client, one separately hosted model container and one remote inference API using synthetic tasks. Verify capability negotiation, client revocation, per-list isolation, rejected write scopes, revision conflicts and deduplicated operations. Test malformed output, unauthorized tool requests and instruction-like content in calendar descriptions. Disconnect all model services and confirm that deterministic scheduling, CalDAV sync and Focus progress still work.

Provider terms, privacy settings, model licenses and runtime dependency licenses must be checked for the selected deployment. No provider or model is preselected by this concept.
