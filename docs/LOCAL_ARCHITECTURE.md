# Current Local Architecture

This document describes the implemented application as of 2026-10-09. Future orchestration requirements are in [ROADMAP.md](ROADMAP.md).

## Services and frameworks

| Service | Framework/runtime | Current responsibility |
| --- | --- | --- |
| ui | React 19 + TypeScript; Vite 8; Tailwind CSS 4; shadcn/ui source components | Conversations/files, OpenAI settings, RAG main-area management, assistant replies/progress/retry |
| core | NestJS 12 + TypeScript; Express adapter; node-postgres (pg) | Chat persistence, health, .env settings, OpenAI discovery/text inference with MCP retrieval; restricted external REST proxy |
| database | PostgreSQL 17 | Chat metadata, ordered messages, attachment metadata and bytes |

Both applications are npm workspaces with one root package-lock.json. TypeScript 5.9 is shared. The exact dependency versions are in the manifests and lockfile. Docker build/runtime stages use Node.js 24.

## Docker runtime

~~~mermaid
flowchart LR
    Browser["Browser"] -->|"127.0.0.1:8080"| UI["ui: Nginx :80<br/>Vite production assets"]
    UI -->|"/api, Compose DNS core:8000"| Core["core: NestJS :8000"]
    Host["Local API client"] -->|"127.0.0.1:8000"| Core
    Core -->|"Compose DNS database:5432"| DB["database: PostgreSQL :5432"]
    Core -->|"HTTPS: models and text inference"| OpenAI["OpenAI API"]
    Core -->|"approved REST and Streamable HTTP MCP"| RAG["Existing external RAG"]
    DB --> Volume["message-data volume"]
~~~

| Service | Image | Dockerfile | Container port | Published host port |
| --- | --- | --- | --- | --- |
| ui | meta-harness-ui:local | [ui/Dockerfile](../ui/Dockerfile) | 80 | 127.0.0.1:8080 |
| core | meta-harness-core:local | [core/Dockerfile](../core/Dockerfile) | 8000 | 127.0.0.1:8000 |
| database | meta-harness-database:local | [database/Dockerfile](../database/Dockerfile) | 5432 | None in full stack |

[docker-compose.yml](../docker-compose.yml) builds and connects all three services on its default local network. Health checks gate database → core → ui startup. All services use the unless-stopped restart policy.

- ui: Node build stage compiles the workspace; Nginx serves ui/dist and proxies /api to core. Browser requests stay on the UI origin.
- core: build stage compiles NestJS; a separate dependency stage installs only core runtime dependencies. The final image runs compiled JavaScript as the node user and includes database/schema.sql plus ordered migrations. Compose injects DB_PASSWORD from the root .env; the secret file is excluded from image build contexts.
- database: PostgreSQL 17 Alpine image with the schema copied to its initialization directory.
- PostgreSQL stores files under /var/lib/postgresql/data, mounted from the Compose message-data volume. Compose prefixes its actual name with the project name, normally networkagent_message-data.

[docker-compose.dev.yml](../docker-compose.dev.yml) adds only a loopback PostgreSQL port, 127.0.0.1:5432, for native development.

## Native development runtime

Vite runs on 127.0.0.1:8080 and proxies /api to NestJS on 127.0.0.1:8000. PostgreSQL runs in Docker with the development override. CORE_PORT can change the native backend and Vite proxy target; the UI port remains fixed at 8080 with strict port selection.

Container core listens on 0.0.0.0:8000 for its Compose peers. Native core defaults to 127.0.0.1:8000. Full-stack published ports remain on loopback.

## Environment and secrets

The root ignored .env is the local source for passwords, API keys, tokens, and future confidential connection configuration. It is owner-readable/writable only. The committed .env.example documents variable names with empty secret values.

Compose resolves DB_PASSWORD and maps it to database POSTGRES_PASSWORD and core DB_PASSWORD. Both are required; there is no fallback password. Only the database credential is injected as a Compose environment value. Core additionally has a runtime read/write bind of the existing root .env at /app/.env, so API-key/configuration writes reach the host file. This mount is outside the image; ui/database have no file mount. The UI receives only the requested masked key metadata.

For native startup, core/src/config/environment.ts loads the repository-root .env using Node's built-in loadEnvFile before Nest creates its modules. Its path is derived from the backend module location, so root/workspace launch directories both work. Existing process environment values take precedence. Missing .env is allowed for a container with injected values, but missing/blank DB_PASSWORD prevents startup. File-read failures produce a generic error without echoing contents.

Non-confidential host/port/database-name defaults remain in source. Future secret-bearing profiles must store environment-variable references, not raw secrets. See [OPERATIONS.md](OPERATIONS.md) for startup and password changes.

## Application structure

### Frontend

App.tsx coordinates the saved-chat list, selected chat, asynchronous loads, send state, and visible errors using React hooks. No browser persistence or global state library is used. Unsaved drafts and selected-chat state live in the current browser session. LlmSettings owns its collapsible form, masked saved-key metadata, remote model list, and unsaved model/thinking preferences. The key-entry value clears on submission and is never stored in browser persistence.

Chat components handle sidebar navigation, composer controls, file cards, message rendering, and SVG icons. Sidebar owns a separate React state for its collapsible Chats title section; collapsing it does not affect active chat/draft state. shadcn Button/Textarea primitives live in components/ui; chat.css controls the reference layout and index.css defines Tailwind/theme tokens. API calls are isolated in lib/api.ts; UI data shapes live in types/chat.ts.

### Backend

AppModule imports ConfigModule, McpModule, RagModule, global DatabaseModule, HealthModule, ChatsModule and LlmModule.

- Controllers handle HTTP routes, UUID parsing, multipart limits, and streamed downloads.
- ChatsService owns chat queries, title generation, user/reply retries, attachment persistence, and serialized chat generation.
- The environment helper loads local settings and requires configured secrets before startup. DatabaseService owns the pg pool, schema initialization, and transaction helper; it receives its password only from environment configuration.
- HttpExceptionFilter gives all request errors a common JSON envelope and keeps internal error details server-side.

LlmModule serves configuration and online model discovery. EnvironmentStore serializes file reads/writes, allows updates to OPENAI_API_KEY, LLM_PROVIDER, LLM_MODEL, LLM_THINKING and generated MCP_TOKEN_<UUID> names, preserves unrelated entries, syncs writes, and attempts restoration on write failure. Model discovery calls the fixed HTTPS OpenAI models endpoint with a 15-second timeout, rejects redirects, and never returns raw provider error bodies.

LlmModule exports its service to ChatsModule for Responses API text inference using current saved settings. Provider errors are converted to fixed messages; raw error bodies are discarded. Configuration/model discovery performs no inference. Core has no ORM, ordered workflow engine or ML/validator executor. Compact retrieval/source traces use messages.tool_calls. Its generic MCP client is described below.

### Persistence and schema

database/schema.sql is the current schema snapshot; database/migrations/ contains immutable upgrades. PostgreSQL applies it when a fresh data directory is initialized. Core reapplies its idempotent statements at startup inside a transaction with an advisory lock, including the explicit ADD COLUMN IF NOT EXISTS upgrade for reply linkage on existing volumes.

This is idempotent schema initialization/upgrading, not a versioned migration system. Future changes need explicit migration design; editing CREATE TABLE IF NOT EXISTS alone does not alter existing tables.

A send locks the chat row, inserts the message and attachment bytes, and updates the title/activity timestamp in one transaction. Reads and downloads use parameterized SQL. See [DATA_MODELS.md](DATA_MODELS.md) and [API_SPEC.md](API_SPEC.md).

## Request flow

1. UI loads saved chat summaries from core.
2. New chat clears the current draft; core creates its row when the first send begins.
3. UI submits text, a message UUID, and optional files using multipart form data.
4. Core validates the submission and commits the message, files, and first-message title.
5. UI adds the saved user message, clears the composer, and requests its assistant response; it shows Responding… and pauses navigation/sends.
6. Core obtains a per-chat PostgreSQL advisory session lock, checks for an existing reply and latest unanswered user, then sends the ordered text history to OpenAI using current .env settings. No SQL transaction is held during the provider request.
7. Core commits the assistant reply and chat activity together, releases the lock, and UI displays the left-aligned answer. A saved reply returns idempotently without inference. User saves acquire a matching advisory transaction lock; concurrent actions get 409.
8. Failed generation leaves the user saved and permits explicit retry. Reopening a chat loads both roles and offers retry for the latest unanswered user. File cards download saved bytes.

Responses requests are stateless (store:false), non-streaming and offer explicitly permitted MCP tools. context-window.ts counts actual input, compacts it at 90% using the selected model and preserves the complete returned window. ChatsService commits private model context plus a position watermark with the final reply; the visible transcript remains intact. Budget checkpoints return control to React, which requests the next prompt with fresh budgets. Private tool state preserves confirmations/completed effects across requests. Limits and compatibility are owned by API_SPEC.md; token capacities by OPERATIONS.md. Attachments are stored/downloaded, not analyzed or ingested into RAG; only their names and a contents-unavailable note enter model input.

## LLM configuration flow

1. UI reads masked configuration from GET /api/llm.
2. Entering/saving a key sends it once to PUT /api/llm; core updates only its allowlisted .env entries.
3. UI discards the input and reads the four-character-plus-stars mask.
4. GET /api/llm/models retrieves sorted/deduplicated IDs from https://api.openai.com/v1/models using the saved server-side key.
5. Saving a selected model rechecks its availability and persists LLM_MODEL/LLM_THINKING.

All key/model routes use no-store response headers. Settings writes reject unexpected fields and foreign browser origins. The runtime user defaults to UID/GID 1000; LOCAL_UID/LOCAL_GID can match the host .env owner.

A file bind cannot be atomically renamed. Writes are serialized in place with sync and attempted rollback; this is one-core local persistence, not crash-proof secret storage. See OPERATIONS.md for mount/permission and external-edit behavior.

## MCP registry and standalone retrieval

Core's `McpModule` uses the official TypeScript MCP SDK for generic Streamable HTTP discovery. A shared global `ConfigModule` provides the serialized environment store to both LLM and MCP services. Connections/discovered tool schemas/explicit allowlists persist in `mcp_servers` in the existing database; bearer values stay in root `.env`. Registration/discovery remains independent; enabled RAG profiles can supply explicitly permitted read-only functions to the existing Responses chat loop. RagModule proxies allowlisted external REST operations.

`rag-server/` is a separately buildable/deployable Python 3.12 service: FastAPI/Pydantic, SQLAlchemy/Alembic, PostgreSQL 17/pgvector/FTS, LlamaIndex semantic splitting, local HuggingFace embeddings, optional local cross-encoder and Python MCP SDK. Its Docker image serves API/MCP and a separate same-image ingestion worker. The worker's durable queue uses document state/JSONB and advisory locks, with no new domain/queue tables or queue service. It has its own PostgreSQL, original-file and model-cache volumes and no frontend/generative model. Default host port is **127.0.0.1:8090**; database stays private.

`manufacturing-demo/` is an independent optional synthetic example, not a core/RAG dependency. Compose runs PostgreSQL 17 privately and one Python 3.12 FastAPI/SQLAlchemy/pandas/scikit-learn/joblib image for the REST API and official Python MCP SDK Streamable HTTP endpoint. The host API port is **127.0.0.1:8100**; Meta-Harness uses **http://manufacturing-ml:8000/mcp** over the shared `meta-harness-mcp` network. Named volumes persist the seeded database and atomically deployed model. Its internal schema includes products, a frozen evaluation snapshot and durable training jobs. See [manufacturing demo README](../manufacturing-demo/README.md) for commands and ownership.

The optional bridge files attach core and RAG API to external Docker network `meta-harness-mcp`; API alias `rag-api:8090` is reachable from core. Neither database nor ingestion worker joins that bridge. Standalone RAG works without it. Its complete architecture/schema/runtime specification is in [rag-server/README.md](../rag-server/README.md).

## RAG management boundary

RagNavigation replaces the old MCP form. RagWorkspace manages profile selection and opens main-area Connection/Management views; the hidden chat subtree stays mounted to preserve drafts. Shared dark form/actions, Radix dialogs and searchable device selectors reuse the existing UI. lib/rag-api.ts isolates the typed proxy API and complete bounded remote catalogs.

RagService reuses McpService and the shared EnvironmentStore for persisted settings/token references, separate tests, disconnect/permissions and REST targets. rag-client.ts normalizes fixed errors, bounded responses, multipart and timeouts. network-policy.ts is shared by MCP and REST, using exact approved origins, actual socket DNS checks and no redirects/cross-origin requests. Knowledge stays wholly external; the existing RAG containers/database/models are unchanged by this integration.

LlmService extends the saved-model path with automatic generic function selection; McpService revalidates discovered permissions before SDK calls. Compact source metadata persists via ChatsService. Durable task execution histories are implemented; operator-designed research workflow templates remain planned. Detailed bounds/failure policy live in MCP_CONTRACTS.md, not a second agent framework.

## Persistent task runtime

TasksModule extends the existing saved-model/MCP orchestration inside core. PostgreSQL leases/advisory locks protect a bounded in-process worker; operation checkpoints and deterministic evidence verification survive restarts. The same process polls schedules and a durable authenticated event inbox. React TASKS views use REST and SSE; no additional application service or database is required. Optional isolated workspace mounting is in docker-compose.tasks-workspace.yml. Detailed execution and safety contracts live in [TASK_EXECUTION.md](TASK_EXECUTION.md). Ports remain unchanged.

Durable task context delivery and automatic prompt checkpoints run inside the existing core worker, with the same LlmService and database. No extra agent, model, service or queue is introduced. [TASK_EXECUTION.md](TASK_EXECUTION.md) owns budgets and evidence access.

## Active manufacturing replacement: ZSK

The current external manufacturing stack is `zsk-service/`: zsk-db reuses the original manufacturing PostgreSQL volume; zsk-ml exposes FastAPI/MCP on loopback 8100 and compatibility alias manufacturing-ml:8000. It uses supplied RandomForest features/causal history instead of the old six-feature LogisticRegression demo. Labels are purged after training; unlabeled measurements/predictions remain separate. Old manufacturing-demo containers are retired; its source/model volume is historical. See the ZSK README for current contracts. No core/UI/RAG behavior changes.

## Independent factory simulation

The user-authorized `factory-service/` FastAPI/Python MCP service owns an authoritative simulated ZSK environment, clock, sensors, diagnostic actions and background monitoring/outbox. It shares the current private ZSK PostgreSQL database through additive migrations, and authenticates to existing ML REST and template-bound core task events. Core continues to own its existing LLM/task/MCP loop; no second agent or queue is introduced. RAG stays external/read-only. React owns Phaser rendering and local monitoring pages. Core proxies authenticated REST/WS without browser secrets.

Optional stack: `factory-service/docker-compose.yml` plus root `docker-compose.factory.yml` and existing MCP/ZSK bridge overlays. Host factory port **127.0.0.1:8110**; frontend/core/ZSK ports remain 8080/8000/8100. Private database ports stay unexposed in runtime. Isolated recovery tests alone bind 15437/18110/18097 to loopback. See [Factory architecture](FACTORY_ARCHITECTURE.md) and [startup](../factory-service/README.md).
