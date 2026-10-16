# MCP Integration Contracts

## Implemented external RAG integration

The generic MCP Streamable HTTP registry owns server profiles, descriptions, credentials by environment reference, discovered schemas, enabled state and per-server explicit tool permissions. The MCP sidebar opens main-area connection management. RAG adds REST configuration to the same registry; its agent permissions remain read-only. REST knowledge management and MCP agent retrieval are independent. API shapes are in [API_SPEC.md](API_SPEC.md), startup and origin approval in [OPERATIONS.md](OPERATIONS.md), persistence in [DATA_MODELS.md](DATA_MODELS.md).

The official TypeScript SDK initializes, discovers and executes tools. Discovery never calls them. Expected external RAG tools are find_device, get_device_issues, search_knowledge and get_document_context; availability and input schemas come from the actual server. Test reports whether it discovers read-only search/retrieval metadata. Chat receives only discovered read-only tools in the operator's saved allowlist, on connected, enabled, non-disconnected RAG profiles. Other servers remain configurable; no vendor-specific dispatch or server-side inferred device identity is introduced.

### Network and credentials

HTTP(S) URLs must match an exact operator-approved origin from root `.env` RAG_ALLOWED_ORIGINS. Reject embedded credentials/query/fragment. A shared guarded HTTP adapter forbids redirects and cross-origin SDK requests, validates literal addresses and every address returned by DNS at actual socket connection, and rejects metadata/link-local/reserved/multicast ranges. Local loopback/private Docker addresses are allowed only under approved origins. This prevents arbitrary backend URL forwarding and DNS-rebinding between validation and connection. Outgoing requests have bounded bodies/timeouts; no shell/stdio runner exists.

Credentials resolve from root `.env` on calls. UI token input is write-only, cleared on submission, and stored under a generated environment name; SQL holds its reference. Public profiles expose only a saved-credential flag/reference. Fixed upstream errors omit credentials/raw upstream responses; tool output redacts configured secret values before model use. Discovery sanitizes its bearer value from names/descriptions/schemas.

Read-only annotations are advisory: the operator must trust the server and explicitly select tools. Arguments validate against discovered JSON Schema; remote regular-expression schemas are rejected to avoid unbounded regex execution. No remote schema fetching occurs. Input/catalog/output sizes, call counts and durations are bounded. Permission/status/metadata are rechecked immediately before execution, so revocation or disconnect blocks stale model tools.

### Existing saved-model chat loop

The existing OpenAI Responses path uses current model/thinking, tool_choice auto, sequential function calls and discovered schemas. Function names are stable hashes of server/tool identity, avoiding collisions. A bounded server-side continuation persists pending invocation and tool results with the message so confirmations survive reload and provider retries do not replay external calls. See the [official Responses function calling guide](https://developers.openai.com/api/docs/guides/function-calling).

No MCP call is forced for ordinary messages. Each prompt is bounded to eight provider turns, twelve tool calls and a two-minute deadline; budget checkpoints let the UI request the next prompt automatically. MCP retains its 20-second session/15-second call bound. Context compaction and continuation safeguards are owned by API_SPEC.md. The model is told that descriptions/passages are untrusted data, possible causes are hypotheses, ambiguous devices require explicit identification, and ranking scores are not diagnostic confidence.

Read-only tools execute only when discovered, connected, enabled and explicitly allowed. State-changing tools additionally pause for the user to confirm the exact tool and arguments; the confirmation is expiring and single-use. Denial never invokes the tool. An interrupted execution is not replayed automatically. Tool failures return a fixed error as function-call output; network failures mark the MCP connection failed for retesting. Provider errors preserve saved user/tool results for retry. Messages record bounded server/tool/result summaries, success and source references. Logger entries omit arguments/passages/secrets. Generated response text remains distinct from retrieved source metadata. This is a compact chat trace, not full workflow history.

The independent [`manufacturing-demo/`](../manufacturing-demo/README.md) is a synthetic-data REST/MCP example; it owns its model/database and exposes no generative LLM. Generic registry code has no manufacturing-specific dispatch.

## Planned ordered workflows

[ROADMAP.md](ROADMAP.md) owns unimplemented control-plane/workflow requirements. Future ML steps bind server_id/tool_name/input mappings/output names with explicit configured order. Core must remain generic. Analyzer input may include prompt, selected earlier outputs and configured retrieval context. External validation follows the candidate answer and preserves its result separately; no silent rewrites.

Future immutable run records must preserve workflow/version, call order, sanitized mappings/results/errors, timings, candidate answer, evidence and validator results. Those schemas/routes do not exist yet. Current chat attachments stay local and are not automatically ingested; explicit RAG upload uses the external REST API. Core owns no chunking, embedding, ranking, RAG database or external validator business logic.

## Persistent task integration

The task worker uses the same discovered tool registry, schema validation, network adapter and permission checks. Explicit controlled-tool task grants are bound to stable connection/schema/allowlist metadata. Dangerous task tools require exact approvals. Operation IDs are sent as idempotency metadata; unknown write outcomes pause for reconciliation, with no assumption that the remote service honors idempotency. Full task execution evidence and retries persist separately from compact chat traces. Execution policy and verification contracts are owned by [TASK_EXECUTION.md](TASK_EXECUTION.md).

## ZSK manufacturing replacement

Existing manufacturing profile now discovers eight generic ZSK tools at the retained manufacturing-ml alias. No core tool-name branching was added. Read credential ZSK_API_KEY is used with five explicit read-only permissions. State-changing add/train/batch calls require an admin credential, explicit operator allowlist, existing exact confirmation/task policy and stable idempotency key. Current model labels were removed after training; retraining requires new verified labels. Current contracts and units are in zsk-service/README.md.

## Factory simulation MCP

Independent Factory MCP registers through the existing generic interface at `http://factory:8110/mcp`, root credential variable `FACTORY_MCP_AUTH_TOKEN`. Nine read/eight simulation-write tools are documented in [factory README](../factory-service/README.md); schemas reject extra properties. Operator discovery/allowlists remain required. Controlled task grants are explicit and bound to tool configuration; backend simulation permissions are an additional boundary. No physical equipment tools exist.

Every simulation machine/technician write requires episode identity. The server reads official Python SDK request context and prioritizes harness `Idempotency-Key` / `_meta.operationId` over model optional keys. Action acknowledgment is committed evidence, not completion. Inspection completion can be scoped to the same epoch/component/alarm and its time. After response loss the harness's existing UNKNOWN reconciliation gate remains authoritative. ZSK adds read-only `get_zsk_forecast_metrics` and `predict_zsk_future_failure`; current-health tools remain unchanged. RAG tools/permissions remain read-only and source attribution is preserved.
