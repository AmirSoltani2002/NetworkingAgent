# Persistent agent tasks

## Run and use

Run the existing stack with `docker compose -f docker-compose.yml -f docker-compose.mcp.yml up -d --build`. No task microservice or new database is required. The core image runs a bounded background worker and scheduler inside NestJS.

In chat, select **Run as task**, enter an objective, and send it. Ordinary chat remains the default. Alternatively open **TASKS → Active Tasks → New task**. Optional checked MCP tools grant controlled write permission for this task only (the operator must first classify these exact tools in TASK_CONTROLLED_MCP_TOOLS); otherwise writes request approval. Connected tools still require the existing operator allowlist.

TASKS contains Active Tasks, Task History, and Scheduled Tasks. Details show the immutable plan/criteria, actual verified progress, next action, tool requests/results, approvals, errors, and retries. Pause, resume, cancel, retry, approve/reject, and reconciliation controls persist across reloads. Chat submissions stay in chat. Every task-owned message has a live response card with status, a readable outcome, expandable tool requests/results and redacted model outputs, and an opt-in View task details link. Cards survive reload through per-message task IDs. Updates arrive through SSE with polling fallback. Completed replies are added to the original conversation.

## Persistence and concurrency

The existing PostgreSQL database stores `agent_tasks`, `task_steps`, `task_operations`, `task_approvals`, `task_verifications`, `task_events`, `task_schedules`, `task_triggers`, and `task_trigger_events`. Foreign keys cascade from conversations to task history. Trigger/schedule IDs remain in task source metadata after configuration deletion.

`database/schema.sql` is the current schema snapshot. Ordered, checksum-protected SQL migrations live in `database/migrations/`; startup applies them under the existing database advisory transaction lock and records them in `schema_migrations`. Migration 001 adds task persistence; 002 adds cost-budget accounting; 003 adds context delivery fingerprints, prompt-budget baselines and a continuation counter. Never edit an applied migration.

Workers claim due rows with `FOR UPDATE SKIP LOCKED`. A session advisory lock prevents simultaneous execution even when a lease expires; a UUID owner fences checkpoints and dispatch. Heartbeats extend a 30-second lease. Expired RUNNING tasks resume after restart. Every model decision, dispatch, result, approval, verification, and retry is committed independently. Limits prevent indefinite execution.

## Agent and completion

The existing `LlmService`, saved model/key, Responses API, and MCP registry are reused. Structured decisions select one action per worker slice. Model response text is redacted and saved in model_output events (32,000-character display limit). The parser accepts one schema-valid JSON decision surrounded by prose or Markdown fences, using quote/escape-aware brace scanning. Explanations remain in recorded model outputs. Repeated execute/wait objects are collapsed only when all operational fields are identical and differences are limited to step/summary wording. Conflicting decisions, invalid schemas, and malformed nested JSON never dispatch actions; they request another decision with bounded retries. Response parsing is bounded to 262,144 characters and 512 JSON objects. Argument filters accept JSON pointers or plain exact property names; plain names are escaped as one pointer token, not interpreted as nested paths. On retry, a saved completion response is reused only if the actual persisted evidence now passes every immutable criterion, avoiding redundant tool/model calls. Non-execution decisions carry no action; irrelevant command/workspace MCP-argument placeholders are not parsed. Empty criterion placeholders mean no argument filters and a null expected value; malformed nonempty JSON is rejected. Vague or incomplete requests are interpreted using up to 20 prior conversation messages (4,000 characters per message) and discovered tool metadata. The model chooses a useful conservative scope, states its assumptions, and proceeds; ambiguity alone is not a reason to stop. Registered/allowlisted tools remain the only external capabilities. A fresh blocked decision without existing criteria is delivered as a direct response, preserving its explanation without executing unsafe or unavailable actions. Blocked tasks with existing external criteria preserve their pause reason. External execution and completion still require measurable criteria. A respond decision can deliver an informational or best-effort answer without tools. For a fresh response-only task, the backend stores an internal response operation and verifies nonempty delivery; this does not verify any external action. Existing external criteria stay immutable: a partial response is shown in chat, and the task remains paused if actual completion checks fail. Task timestamps retain ISO serialization through secret redaction. At 90% of the model context budget, the same model compacts its private task context. Full operation evidence remains in PostgreSQL. Context updates are incremental: recent conversation and tool schemas seed a prompt once; changed tool schemas and operation results are delivered using fingerprints committed atomically with the model window. Large results use 12,000-character previews, with up to 64,000 characters of changed evidence per update. A compact ledger (latest 40 operations) and deterministic check statuses remain available. The model can select an internal evidence action to page exact stored results by task-owned operation ID and JSON pointer. These reads never call external tools and cannot replace external completion evidence. Arrays return at most 50 items, with character bounds; nested oversized items can be read through a more specific pointer. Invalid evidence reads return a recorded result for correction rather than replaying an external request. Snapshot tool output/descriptions are untrusted data.

The first decision defines measurable completion criteria; later model decisions cannot replace them. The backend evaluates JSON-pointer predicates against successful stored operations, with optional exact argument filters for devices/jobs. Supported checks are exists, equals, nonempty, gte, and contains. Verification rows identify actual operations/values. A generated summary alone cannot verify external task completion. Response-only tasks verify delivery of the saved answer, explicitly distinguished from tool execution. Progress represents passed checks, not invented processing percentages. Operator reconciliation does not count as verification evidence; fresh reads are required.

The planner must select a stable zero-based plan step. Completed write results are reused by both plan-step identity and canonical argument identity. A task can span many model turns and worker slices; it continues without browser requests.

## Retry and write safety

Transient provider/network/service failures retry with exponential backoff, jitter, and provider Retry-After information. Read-only MCP tool-level errors preserve the rejected result, mark the operation/step failed, clear the pending action and request a fresh model decision after backoff. The model can resolve identifiers and correct arguments; these recovery attempts share the configured retry/turn/time budgets. Retrying an older failed read-only tool request also replans instead of replaying its rejected arguments. Authentication and permission failures still stop. Read-only MCP connections may rediscover only an enabled, permitted, non-disconnected profile. Operator revocation remains effective.

Each operation has a durable UUID and state ledger. MCP dispatch sends it in `Idempotency-Key` and request `_meta.operationId`; external servers may ignore these, so exactly-once execution is **not** assumed. Dispatch is recorded immediately before sending. Completed writes are never replayed. A write interrupted after dispatch, or returning an ambiguous error, becomes UNKNOWN and pauses the task. Check the external service, record **Succeeded externally** or **Definitely not executed** with an explanation, then resume. The declaration resolves replay safety and is audited; it cannot fabricate successful completion checks. Cancellation cannot undo an external action already sent.

## Local execution policy

Local operations are disabled until `TASK_WORKSPACE_ROOT` is configured. An optional Docker workspace override mounts only `./task-workspace` at `/workspace`; it does not mount the repository or Docker socket. Native execution can use an explicitly approved project directory.

The backend accepts structured operations rather than shell strings:

- Safe: workspace read/list/exists; pwd; cat of one approved file; grep with `-F`, a literal and a file; bounded ls/find; git status `--short` or diff `--stat` in an ordinary approved repository.
- Controlled: bounded atomic workspace file writes and MCP writes explicitly classified in TASK_CONTROLLED_MCP_TOOLS. These require exact approval or an explicit task grant (MCP only).
- Dangerous: deletion of one regular workspace file, unclassified MCP writes, and MCP tools listed in `TASK_DANGEROUS_MCP_TOOLS`. These require exact action approval every time; broad task grants cannot authorize them.

Shell chaining/substitution, arbitrary executables, SQL, Python, downloaded scripts, recursive deletion, protected paths, and escaping symlinks are rejected. Commands use fixed binaries, parsed argument grammars, no shell, a minimal environment without credentials, 10-second timeouts, and bounded output. File tools use bounded reads, protected-path checks and no-follow opens. Git inspection disables fsmonitor/hooks/external diff/text conversion. Logs/results redact configured secrets. More capable approved test/compilation/install/Docker operations must be supplied by an operator-controlled external MCP runner; no host Docker socket or arbitrary command facility is added.

## Schedules

Schedules support one-time ISO dates or cron expressions with IANA time zones. Due executions and schedule advancement commit in one transaction. A unique occurrence key prevents duplicate tasks. Missed recurring occurrences coalesce into one catch-up task after restart. Enable, disable, edit, delete, and history endpoints remain available. Invalid templates are disabled with a persisted explanation.

Event triggers are temporarily removed: no navigation, configuration endpoints, webhook intake, completion-event publication, or event dispatcher is active. Historical trigger/inbox tables and immutable migrations are retained without processing their contents. Existing tasks already created from events remain ordinary durable tasks.

## Configuration

All settings are read from root `.env` before native/container startup. Examples contain no secrets.

| Variable | Default | Purpose |
| --- | --- | --- |
| TASK_WORKER_ENABLED | true | Run worker and schedule polling |
| TASK_CONCURRENCY | 2 | Concurrent worker slices, maximum 4 |
| TASK_MAX_TURNS | 8 | Model decision attempts per prompt, including invalid responses |
| TASK_MAX_TOKENS | 200000 | Provider token budget per prompt |
| TASK_MAX_ACTIVE_MS | 120000 | Active execution time per prompt; approval wait excluded |
| TASK_MAX_CONTINUATIONS | 20 | Maximum automatic prompt checkpoints per task; then pause |
| TASK_MAX_RETRIES | 5 | Retry attempts for a failing checkpoint |
| TASK_WORKSPACE_ROOT | empty | Approved workspace; empty disables local tools |
| TASK_CONTROLLED_MCP_TOOLS | empty | Operator-reviewed `server-uuid:tool` eligible for task grants; other writes require exact approval |
| TASK_DANGEROUS_MCP_TOOLS | empty | Comma-separated `server-uuid:tool` requiring exact approval |
| TASK_MAX_COST_USD | empty | Optional cost-estimate budget |
| TASK_TOKEN_COST_USD_PER_MILLION | empty | Conservative maximum token price for selected model; required with cost budget |

At a turn/token/active-time boundary the worker asks the selected model for a bounded factual working memo, commits a new private window and budget baselines, and automatically continues in a fresh prompt. Existing legacy task windows receive one such checkpoint when next resumed. Pending actions, immutable criteria, grants, approvals and operation identities survive; completed writes are never repeated. The original transcript and full evidence are retained. Summary failure retries preserve the original window. A cost or continuation cap pauses with saved progress rather than claiming completion. Resume requires increasing the exhausted operator cap; it does not erase lifetime accounting.

Lifetime tokens, model attempts, active time and estimated cost remain cumulative across prompts. Provider usage from malformed/incomplete responses and successful compaction/summary requests is counted when returned. The cost is an operator-priced estimate, not billing reconciliation; requests interrupted before usage returns may still incur charges. Limits are checked between slices and an in-flight request can cross a budget. Each slice retains its two-minute deadline. Provider/model context capacity remains configured through existing LLM settings; the 90% context threshold is distinct from the per-prompt execution budget.

## REST API

- `GET/POST /api/tasks`; list uses `history=true`, `limit`, `offset`.
- `GET /api/tasks/{id}`, `/steps`, `/events`; `GET /api/tasks/stream` SSE.
- `POST /api/tasks/{id}/pause|resume|cancel|retry`.
- `POST /api/tasks/{id}/approve`: `{approvalId,approved}`.
- `POST /api/tasks/{id}/reconcile`: `{operationId,outcome,reason}`.
- `GET/POST /api/schedules`, `PUT/DELETE /api/schedules/{id}`, `POST /enabled`, `GET /history`.
- `GET /api/task-policy`, `POST /api/task-policy/check`.

Task body: `{request,conversationId?,messageId?,grants?:[{serverId,tool}],dedupeKey?}`. An existing message must belong to that conversation and match the request. Ordinary reply generation is blocked for a task-owned message. Schedule body: `{name,enabled,kind,cron?,timezone,runAt?,template:{request,conversationId?,grants?}}`.

Local mutation routes follow existing origin restrictions. The application remains loopback-only; no new multi-user authentication boundary is implied.

## Verification

Run `npm test`, `npm run typecheck`, `npm run lint`, and `npm run build`. Database tests require `CORE_TEST_DATABASE_URL` ending in `_test` or `_tests`; never use the application database. `core/tests/tasks-database.test.cjs` checks actual PostgreSQL claims, checkpoints, approvals, verification, retries, unknown outcomes, cancellation, schedules, and event deduplication.

The restart fixture is test-only: start `core/tests/task-restart-fixture.cjs` in an isolated core-image container named `meta-harness-task-restart-test`, with the test database and port `127.0.0.1:18098:8098`. Run `python3 core/tests/task-restart-review.py`. It sends SIGKILL during a read after a committed MCP write, restarts the container, and checks one write, two read attempts, and COMPLETED verification. It uses the real worker, PostgreSQL and official MCP SDK with a deterministic planner, not paid model calls. Results are recorded in `docs/verification/task-restart.json`.

## Limits

Criteria are proposed by the saved LLM and enforced deterministically; accurate criteria still depend on available tool schemas/results and the model’s interpretation of the objective. Unsupported capabilities pause or fail with an explanation. No live paid OpenAI task was required by automated tests. There is no generic external-write status resolver: ambiguous operations require operator reconciliation. Event triggers are currently unavailable. No arbitrary shell or production infrastructure control is provided.

## Template-bound factory events and planner submission

Factory alarms enter authenticated `/api/internal/task-events`, using tracked templates/grants/immutable checks and atomic source/event receipts; they reuse this engine rather than calling an LLM directly. This scoped integration does not restore general event triggers. Factory tools are simulation-only. See [Factory architecture](FACTORY_ARCHITECTURE.md).

Model planning now forces exactly one strict native `submit_task_decision` function with parallel calls disabled. It only submits a proposal to the harness; schema parsing, checkpointing, policy, tool allowlists, explicit task grants/exact approval and deterministic completion remain this engine's responsibility. Multiple calls/text decisions and incomplete outputs dispatch nothing. Function call/output pairing persists in private context, with acknowledgment explicitly saying execution has not occurred. Usage remains recorded; incomplete-response retries expand bounded allowance up to 32,768 tokens/context capacity. Lifetime/prompt/continuation caps remain enforced. Tests cover this behavior and SIGKILL recovery after a completed write on isolated databases.

Task snapshots also carry authoritative `executionScope.grantedControlledTools` (server/tool only, no private policy digest) on every prompt, including reconstruction after a checkpoint. This exposes the already-authorized scope to the model; it does not create grants. Backend configuration/policy remains the enforcement authority. Exact JSON duplication between MCP text and structured content is omitted only from model previews after canonical equality verification; distinct text stays, and full original stored results remain accessible through task-owned paging. These changes address a real conservative partial-response test caused by missing visible grant context and crowded evidence previews.
