# Local Meta-Harness — Engineering Contract

## Working agreement

Implement the user's requested step only. The user owns the research goal and product boundary; the implementation engineer owns routine design choices. Record non-trivial choices in [implementation decisions](docs/IMPLEMENTATION_DECISIONS.md). Ask only when a change affects the product boundary, operator-visible workflow, research scope, or connected-data safety.

## Current implementation

This is a local chat application with OpenAI configuration, external RAG management, generic MCP tools and a separate synthetic manufacturing ML demonstration. Persistent agent tasks and schedules are implemented in core. Event triggers are temporarily removed; historical tables remain inert.

| Service | Stack | Responsibility | Default host port |
| --- | --- | --- | --- |
| ui | React 19, TypeScript, Vite 8, Tailwind CSS 4, shadcn/ui | Saved conversations, message/file composer, response progress/retry, OpenAI settings and collapsible RAG management | 8080 |
| core | NestJS 12, TypeScript, Node.js 24 in Docker | Chat persistence, masked LLM settings, online model discovery, OpenAI text inference with permitted MCP retrieval, external REST proxy | 8000 |
| database | PostgreSQL 17 | Chats, messages, attachment bytes | Private; 5432 in native-development override |

Use these user-selected frameworks. The repository uses npm workspaces for ui and core, one root lockfile, and three local Docker images. Full-stack host ports bind to 127.0.0.1.

Generic MCP registration, descriptions, discovery, explicit permissions, enable/disable and reconnection are implemented. The saved-model Responses loop can select permitted tools from any connected enabled server. State-changing calls require explicit confirmation of the exact invocation; persisted continuation/results prevent automatic replay after a provider failure. Compact tool/source/result summaries live on messages. Persistent task checkpoints, operation ledgers, deterministic completion checks, approvals and restart recovery are implemented; see [TASK_EXECUTION.md](docs/TASK_EXECUTION.md). Separate operator-designed research workflows/validators remain in [ROADMAP.md](docs/ROADMAP.md).

Chat model context is counted before inference and compacted at 90% using the selected model. Private context windows persist separately from the visible transcript. Durable task context uses incremental evidence delivery, task-owned stored-result paging and selected-model summary checkpoints; prompt budgets automatically continue while lifetime accounting and hard caps persist. Budget checkpoints automatically request the next prompt through the existing UI; confirmation/replay gates still apply. API_SPEC.md owns limits; OPERATIONS.md owns context-capacity defaults and the root .env override.

## Fixed product boundary

- Local only: no AWS, Terraform, Kubernetes, cloud queues, serverless functions, managed vector databases, or production deployment infrastructure.
- ui owns the browser interface. core owns the local API and, when authorized, generic MCP orchestration and persisted configuration/run history.
- database is the local PostgreSQL persistence service. Keep the schema snapshot in database/schema.sql and immutable upgrades in database/migrations/.
- ML services, RAG engines, deterministic validators, and domain-data providers are external MCP services. Keep their business logic outside core. The user-authorized `rag-server/` is a standalone external retrieval service with its own Python stack, database and image; it must operate without the Meta-Harness. Mock services belong only in test/development fixtures.
- Keep orchestration generic: configured server/tool metadata must determine calls; no vendor-name or BGP-specific branching.
- Connected tools must be discovered and explicitly allowlisted by the operator. Read-only calls may be selected by the saved model. Ordinary chat writes require exact, expiring, single-use confirmation. Durable tasks may use explicit per-task controlled-tool grants; dangerous actions always require exact approval. A prompt alone is not a broad execution grant. RAG permissions remain read-only. No arbitrary SQL, shell or Python execution tools.
- Keep every password, token, API key, and future confidential connection setting in the root ignored .env. Examples contain names and empty values only; no hardcoded or fallback credentials.
- Native core loads the root .env before startup. Compose injects DB_PASSWORD and bind-mounts only the root .env into core for the user-authorized settings writes. Never copy .env into images, mount it into ui/database, or pass secrets into frontend assets.
- The LLM key-entry route may accept a new API key once and save it in .env. Reads return only its first four characters followed by stars, as requested; no reveal endpoint/control exists. Clear the key input on submission. RAG token entry is write-only and saves generated MCP_TOKEN_<UUID> entries in root .env; reads expose only a saved-credential flag. MCP database profiles reference environment-variable names instead of raw credentials. Never return full secrets, log them, include them in traces, commit them, or store them in browser local storage.
- Update the owning specifications and file map whenever configuration, structure, ports, or secret handling changes.

RAG and MCP have independent collapsible sidebar navigation. MCP → Connections/Add MCP Server opens generic management in the main area. Preserve chat/draft/composer state while navigating. Training confirmation appears in the existing conversation.

Future workflow behavior and completion criteria have one source: [ROADMAP.md](docs/ROADMAP.md). MCP mapping, evidence, and error contracts are in [MCP_CONTRACTS.md](docs/MCP_CONTRACTS.md).

## Required reading

Before implementation, read the relevant current specifications:

1. [LOCAL_ARCHITECTURE.md](docs/LOCAL_ARCHITECTURE.md): service boundaries, runtime flow, frameworks, Docker and ports.
2. [UI_SPEC.md](docs/UI_SPEC.md): approved appearance and implemented interactions.
3. [DATA_MODELS.md](docs/DATA_MODELS.md): current persisted entities.
4. [API_SPEC.md](docs/API_SPEC.md): implemented HTTP routes.
5. [MCP_CONTRACTS.md](docs/MCP_CONTRACTS.md): implemented generic MCP registry, network policy, agent invocation/confirmation, plus future workflow boundaries.
6. [ACCEPTANCE_TESTS.md](docs/ACCEPTANCE_TESTS.md): current checks, recorded validation, and remaining coverage.

Use [OPERATIONS.md](docs/OPERATIONS.md) for startup/environment details and [PROJECT_MAP.md](docs/PROJECT_MAP.md) for file ownership. Use [.agent/PLANS.md](.agent/PLANS.md) for significant implementation plans.

## UI reference workflow

Capture screenshots of the rendered application, compare them visually with the user's reference images, and iterate within the requested scope. Inspect the final screenshots before reporting completion.

Preserve the approved black chat layout, automatically titled, independently collapsible Chats section in the sidebar, functional file picker, and Send control. Unused controls were removed at the user's request; do not add decorative or disabled controls.

## Documentation and verification

Update the document that owns a changed behavior; avoid duplicating specifications across files. Separate implemented behavior from planned behavior. Remove superseded documents after preserving relevant decisions in the canonical files.

Report the checks actually performed. The repository has build/typecheck/lint, Vitest UI tests, Node core/SDK tests and optional isolated PostgreSQL tests, plus independent RAG pytest/Docker checks. Do not claim future workflow acceptance has passed.

## Standalone RAG service

For `rag-server/` changes, read its [README](rag-server/README.md), environment example and migrations. Use Python 3.12+, FastAPI, Pydantic, SQLAlchemy, Alembic, LlamaIndex semantic splitting, local HuggingFace embeddings and Python MCP SDK. Exactly six domain tables live in its Alembic migrations; do not modify the chat database for retrieval data. RAG PostgreSQL/pgvector, API/MCP (loopback 8090) and same-image ingestion worker form an independent three-container stack. No RAG frontend, chatbot, generative LLM, external AI API key or automatic evidence linking. Secrets in this checkout remain in root `.env`; standalone copies use their own ignored `.env`. Models/files/database persist in separate volumes. Test only isolated databases whose names end in `_test`/`_tests`.

The optional `docker-compose.mcp.yml` and `rag-server/docker-compose.meta-harness.yml` connect core to the external service through `meta-harness-mcp`. Registry/tool execution remains generic; core guards approved origins and actual DNS/socket resolution. Only the operator-approved retrieval tools may be selected by chat. RAG business logic and knowledge stay external.

## Synthetic manufacturing demonstration

`manufacturing-demo/` is the user-authorized independent example, not core business logic. Read its [README](manufacturing-demo/README.md) before changes. Python 3.12/FastAPI, SQLAlchemy, pandas, scikit-learn Pipeline/LogisticRegression and joblib share one ML/MCP image; a private PostgreSQL 17 container owns synthetic products, a frozen evaluation snapshot and durable training jobs. Host ML port is 127.0.0.1:8100; bridge MCP URL is http://manufacturing-ml:8000/mcp. Keep 0=Defective and 1=Good, never overwrite ground truth, never train on frozen test identifiers, and atomically replace only successfully validated trusted local artifacts. Training runs in the existing service's background worker. Secrets use MANUFACTURING_DB_PASSWORD/MANUFACTURING_API_KEY in root .env. No new reasoning LLM/agent, frontend, cloud service, or change to RAG internals. Test databases must end in _test/_tests.

## Durable task execution

Read [TASK_EXECUTION.md](docs/TASK_EXECUTION.md) before task changes. Reuse the existing LlmService and MCP registry; no second agent/model/database/queue service. Enforce policies in core, persist before dispatch, never replay completed writes, and pause ambiguous writes for reconciliation. Dangerous actions always require exact approval. Structured local tools are confined to TASK_WORKSPACE_ROOT; no arbitrary shell/code/SQL or host Docker socket. Task grants are explicit, per-task, and bound to current tool configuration. Scheduled tasks retain their configured scope. Event-trigger configuration and execution are temporarily removed. Test restart recovery and concurrency only in an isolated `_test`/`_tests` database. Secrets remain in root .env.

## Current ZSK replacement

The active manufacturing example is now `zsk-service/` (FastAPI/Python MCP SDK/RandomForest), reusing the dedicated manufacturing PostgreSQL volume. Read its README before changes. The supplied labeled ZSK data are used once for training, then removed and replaced with 1,000 unlabeled readings as explicitly requested. Never seed labels again on restart or train from predictions/unlabeled rows. The previous `manufacturing-demo/` is historical and must not be restarted against the replaced DB. Core/chat/RAG are unchanged. Port 8100 and bridge alias manufacturing-ml remain; secrets ZSK_API_KEY/ZSK_ADMIN_API_KEY and existing MANUFACTURING_DB_PASSWORD belong only in root .env.

## User-authorized autonomous factory simulation

The active user request explicitly extends the local boundary with independent `factory-service/` FastAPI/MCP, authoritative continuous synthetic ZSK state, Phaser inside the existing React UI, ML future-onset baseline, periodic monitoring/outbox and authenticated template-bound existing tasks. Read `factory-service/README.md` and `docs/FACTORY_ARCHITECTURE.md` before changes. Domain behavior stays outside core; do not restore general event triggers or real-machine control. Reuse current ZSK unlabeled data/RandomForest and private DB; never reconstruct purged labels or train from predictions. Simulator truth is separate, unavailable to inference. Root secrets only; browser receives no token. Stop/restart/maintenance defaults false; explicitly authorized stop demo never authorizes physical control. Epoch/operation identity, immutable checks, task grants and UNKNOWN reconciliation remain enforced. Runtime adds loopback 8110; isolated tests require `_test`/`_tests` databases and separate volumes.
