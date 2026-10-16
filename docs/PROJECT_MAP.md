# Project File Map

This map describes maintained source files. Generated node_modules, dist, TypeScript cache files, local .env secrets, and .git history are not source specifications.

## Root instructions and tooling

| File | Purpose |
| --- | --- |
| [AGENTS.md](../AGENTS.md) | Engineering contract: current stack, scope, boundaries, required reading, and UI review |
| [README.md](../README.md) | Short project introduction, Docker quick start, and documentation index |
| [package.json](../package.json) | npm workspaces, Node requirement, shared tools, and root dev/build/typecheck/lint/test commands |
| [package-lock.json](../package-lock.json) | Exact dependency resolution for both workspaces and npm ci |
| [eslint.config.mjs](../eslint.config.mjs) | Shared TypeScript/React Hooks lint rules |
| [.env.example](../.env.example) | Empty secret-variable template for the root local .env; no usable password |
| [.gitignore](../.gitignore) | Exclude local secrets, installed dependencies, build output, and TypeScript caches |
| [.dockerignore](../.dockerignore) | Exclude local credentials, tooling/docs, dependencies, and generated output from image build contexts |
| [.agent/PLANS.md](../.agent/PLANS.md) | Format/lifecycle for significant implementation plans |
| [.codex/config.toml](../.codex/config.toml) | Repository Codex settings and optional reviewer registration; not application runtime configuration |
| [.codex/agents/reviewer.toml](../.codex/agents/reviewer.toml) | Optional reviewer's project-specific instructions |

A local [.env](../.env) is ignored, owner-readable/writable, and holds passwords/tokens/API keys/confidential connection settings. Compose resolves DB_PASSWORD and mounts the file only into core for user-authorized LLM/RAG credential updates; native core loads it before startup. It is never copied into images or UI assets. See [OPERATIONS.md](OPERATIONS.md).

## Docker and database

| File | Purpose |
| --- | --- |
| [docker-compose.yml](../docker-compose.yml) | Services/ports/health/data volume, required DB credential, runtime .env bind for core, and host UID/GID mapping |
| [docker-compose.dev.yml](../docker-compose.dev.yml) | Add only localhost PostgreSQL port 5432 for native development |
| [ui/Dockerfile](../ui/Dockerfile) | Build the Vite UI on Node 24 and package static assets in Nginx |
| [ui/nginx.conf](../ui/nginx.conf) | Serve SPA/assets, proxy /api with a 150-second read timeout, cache assets, and limit upload bodies |
| [core/Dockerfile](../core/Dockerfile) | Compile NestJS, install production dependencies, and run as node on port 8000 |
| [database/Dockerfile](../database/Dockerfile) | Package PostgreSQL 17 with the fresh-volume schema initializer |
| [database/schema.sql](../database/schema.sql) | Tables, constraints/indexes, and idempotent reply/context upgrades for existing volumes |

The image/port table and runtime diagram are in [LOCAL_ARCHITECTURE.md](LOCAL_ARCHITECTURE.md).

## Frontend: ui

| File | Purpose |
| --- | --- |
| [ui/package.json](../ui/package.json) | Frontend dependencies and Vite build/dev/preview/typecheck/Vitest scripts |
| [ui/components.json](../ui/components.json) | shadcn generator configuration, style, aliases, and theme entry |
| [ui/tsconfig.json](../ui/tsconfig.json) | Frontend TypeScript, JSX, module resolution, and @ alias |
| [ui/vite.config.ts](../ui/vite.config.ts) | React/Tailwind plugins, @ alias, localhost port 8080, and API proxy |
| [ui/index.html](../ui/index.html) | HTML document and React root/module entry |
| [ui/src/main.tsx](../ui/src/main.tsx) | Mount App in React StrictMode and load styles |
| [ui/src/App.tsx](../ui/src/App.tsx) | Coordinate chats, selection, user saves, response progress/retry, sidebar state, and errors |
| [ui/src/index.css](../ui/src/index.css) | Tailwind import and shadcn/dark theme tokens |
| [ui/src/chat.css](../ui/src/chat.css) | Reference-matched layout, colors, typography, and mobile rules |
| [ui/src/types/chat.ts](../ui/src/types/chat.ts) | Shared frontend types for chat summaries, history, and pending/saved files |
| [ui/src/types/llm.ts](../ui/src/types/llm.ts) | Public masked LLM configuration, remote catalog, and thinking types |
| [ui/src/components/llm/llm-settings.tsx](../ui/src/components/llm/llm-settings.tsx) | Collapsible OpenAI form, ephemeral password input, masked display, catalog refresh, and model/thinking saves |
| [ui/src/lib/api.ts](../ui/src/lib/api.ts) | Chat/LLM fetch clients, multipart/JSON requests, cancellation, and sanitized user-facing errors |
| [ui/src/lib/utils.ts](../ui/src/lib/utils.ts) | Class-name composition helper |
| [ui/src/components/chat/sidebar.tsx](../ui/src/components/chat/sidebar.tsx) | Sidebar visibility, New chat, independent Chats collapse/expand toggle, saved titles, and active selection |
| [ui/src/components/chat/composer.tsx](../ui/src/components/chat/composer.tsx) | Draft, native file picker, file checks/removal, Enter/Send, and retry UUID |
| [ui/src/components/chat/attachment-card.tsx](../ui/src/components/chat/attachment-card.tsx) | Name/size card for pending files and saved downloads |
| [ui/src/components/chat/message-list.tsx](../ui/src/components/chat/message-list.tsx) | Render user bubbles/assistant text, file downloads, response progress/retry, and scroll to recent content |
| [ui/src/components/chat/icon.tsx](../ui/src/components/chat/icon.tsx) | Reusable SVG controls matching the visual reference |
| [ui/src/components/ui/button.tsx](../ui/src/components/ui/button.tsx) | shadcn Button primitive and variants |
| [ui/src/components/ui/textarea.tsx](../ui/src/components/ui/textarea.tsx) | shadcn Textarea primitive |

## Backend: core

| File | Purpose |
| --- | --- |
| [core/package.json](../core/package.json) | NestJS/pg dependencies and dev/build/start/typecheck scripts |
| [core/nest-cli.json](../core/nest-cli.json) | Nest CLI source/build configuration |
| [core/tsconfig.json](../core/tsconfig.json) | Backend TypeScript, decorator metadata, and dist output |
| [core/src/main.ts](../core/src/main.ts) | Load local environment, require DB_PASSWORD, then bootstrap NestJS, /api prefix, error filter, shutdown hooks, host/port validation |
| [core/src/config/environment.ts](../core/src/config/environment.ts) | Resolve/load root .env, sanitize file errors, and require secrets without fallbacks |
| [core/src/config/local-origin.ts](../core/src/config/local-origin.ts) | Shared loopback-origin guard for settings writes and paid response requests |
| [core/src/config/environment-store.service.ts](../core/src/config/environment-store.service.ts) | Serialize allowlisted .env reads/writes, preserve other entries, detect key-change conflicts, sync/restore writes |
| [core/src/llm/llm.module.ts](../core/src/llm/llm.module.ts) | Register LLM controller/service; environment store is shared by ConfigModule |
| [core/src/llm/llm.controller.ts](../core/src/llm/llm.controller.ts) | Configuration/discovery routes, no-store headers, and local-browser-origin check |
| [core/src/llm/llm.service.ts](../core/src/llm/llm.service.ts) | Settings/masking/catalog persistence, Responses inference, compaction and durable per-prompt checkpoints |
| [core/src/app.module.ts](../core/src/app.module.ts) | Compose ConfigModule, McpModule, RagModule, DatabaseModule, HealthModule, ChatsModule and LlmModule |
| [core/src/http-exception.filter.ts](../core/src/http-exception.filter.ts) | Common request-error JSON and server-side internal-error logging |
| [core/src/database/database.module.ts](../core/src/database/database.module.ts) | Globally provide/export database access |
| [core/src/database/database.service.ts](../core/src/database/database.service.ts) | pg pool/non-secret defaults, required environment password, schema initialization, transactions, and shutdown |
| [core/src/health/health.module.ts](../core/src/health/health.module.ts) | Register the health controller |
| [core/src/health/health.controller.ts](../core/src/health/health.controller.ts) | GET /api/health, including a database query |
| [core/src/chats/chats.module.ts](../core/src/chats/chats.module.ts) | Register chat controller/service |
| [core/src/chats/chats.controller.ts](../core/src/chats/chats.controller.ts) | Chat routes, UUID/multipart validation, and binary download response |
| [core/src/chats/chats.service.ts](../core/src/chats/chats.service.ts) | History/titles/files, user/reply idempotency, per-chat advisory locks, model input, and assistant persistence |

## Documentation ownership

| File | Owns |
| --- | --- |
| [LOCAL_ARCHITECTURE.md](LOCAL_ARCHITECTURE.md) | Implemented service topology, frameworks, modules, Docker image internals, and port table |
| [OPERATIONS.md](OPERATIONS.md) | Startup, native development, environment defaults, logs, volume behavior, and troubleshooting |
| [UI_SPEC.md](UI_SPEC.md) | Current visual/interaction requirements, responsive behavior, and screenshot index |
| [DATA_MODELS.md](DATA_MODELS.md) | Implemented PostgreSQL entities, ordering, title/retry/storage rules, and JSON model notes |
| [API_SPEC.md](API_SPEC.md) | Implemented HTTP routes, request/response shapes, limits, and errors |
| [IMPLEMENTATION_DECISIONS.md](IMPLEMENTATION_DECISIONS.md) | Reasons for current structural choices and their limitations |
| [ACCEPTANCE_TESTS.md](ACCEPTANCE_TESTS.md) | Current acceptance checks, recorded manual/build/lint results, and current coverage gaps |
| [ROADMAP.md](ROADMAP.md) | Unimplemented control-plane/workflow requirements and future completion criteria |
| [MCP_CONTRACTS.md](MCP_CONTRACTS.md) | Current registration/allowlisting and future external-tool mapping/evidence/trace contracts |
| [PROJECT_MAP.md](PROJECT_MAP.md) | File purposes and canonical documentation ownership |

## Visual review artifacts

| File | Purpose |
| --- | --- |
| [screenshots/ui-desktop.png](screenshots/ui-desktop.png) | Clean desktop layout |
| [screenshots/ui-chats.png](screenshots/ui-chats.png) | Saved titles and selected message |
| [screenshots/ui-chats-collapsed.png](screenshots/ui-chats-collapsed.png) | Collapsed Chats section with retained conversation/draft |
| [screenshots/ui-attachments.png](screenshots/ui-attachments.png) | Composer file selection |
| [screenshots/ui-mobile.png](screenshots/ui-mobile.png) | Mobile conversation/composer |
| [screenshots/ui-mobile-chats.png](screenshots/ui-mobile-chats.png) | Mobile saved-chat drawer, expanded section |
| [screenshots/ui-mobile-chats-collapsed.png](screenshots/ui-mobile-chats-collapsed.png) | Mobile drawer, collapsed Chats section |
| [screenshots/ui-llm.png](screenshots/ui-llm.png) | New LLM form |
| [screenshots/ui-llm-saved.png](screenshots/ui-llm-saved.png) | Masking and model/thinking controls with fixture data |
| [screenshots/ui-llm-collapsed.png](screenshots/ui-llm-collapsed.png) | Collapsed LLM section |
| [screenshots/ui-mobile-llm.png](screenshots/ui-mobile-llm.png) | Mobile LLM form |
| [screenshots/ui-assistant.png](screenshots/ui-assistant.png) | Desktop live OpenAI replies and conversation history |
| [screenshots/ui-mobile-assistant.png](screenshots/ui-mobile-assistant.png) | Mobile live assistant replies |
| [screenshots/ui-responding.png](screenshots/ui-responding.png) | Response progress after saving the user |
| [screenshots/ui-response-error.png](screenshots/ui-response-error.png) | Simulated response failure and explicit retry |

These are dated review evidence, not runtime assets or database seed data. LLM saved-state captures use an isolated fixture configuration; inference captures use real saved-model replies, with a browser-intercepted failure for retry review.

## MCP configuration and external RAG files

| File | Purpose |
| --- | --- |
| [docker-compose.mcp.yml](../docker-compose.mcp.yml) | Optional core attachment to the external local MCP network |
| [core/src/config/config.module.ts](../core/src/config/config.module.ts) | One shared global environment store for LLM and MCP modules |
| [core/src/mcp/mcp.module.ts](../core/src/mcp/mcp.module.ts) | Register generic MCP controller/service |
| [core/src/mcp/mcp.controller.ts](../core/src/mcp/mcp.controller.ts) | Registry CRUD/discovery/allowlist routes with UUID and local-origin guards |
| [core/src/mcp/mcp.service.ts](../core/src/mcp/mcp.service.ts) | Connection validation, SQL persistence, secret references, SDK discovery, bounded metadata/allowlists and permitted retrieval execution |
| [core/tests/mcp.test.cjs](../core/tests/mcp.test.cjs) | Official SDK fixture tests for discovery, validation, secrets and permitted execution/revocation |
| [rag-server/README.md](../rag-server/README.md) | Authoritative standalone retrieval architecture, API/MCP/schema, operations, testing and internal file map |
| [rag-server/Dockerfile](../rag-server/Dockerfile) | Python dependency/runtime/test stages; non-root API/MCP and worker image |
| [rag-server/docker-compose.yml](../rag-server/docker-compose.yml) | Independent pgvector/API/worker stack and persistent volumes |
| [rag-server/docker-compose.test.yml](../rag-server/docker-compose.test.yml) | Isolated disposable PostgreSQL and reproducible pytest image target |
| [rag-server/docker-compose.meta-harness.yml](../rag-server/docker-compose.meta-harness.yml) | Optional RAG API bridge/alias for the existing core |
| [rag-server/.env.example](../rag-server/.env.example) / [.dockerignore](../rag-server/.dockerignore) | Secret-free settings template and image-context exclusions |
| [rag-server/.gitignore](../rag-server/.gitignore) | Exclude standalone secrets, models, documents and generated Python output |
| [rag-server/pyproject.toml](../rag-server/pyproject.toml) | Python package metadata and pytest/Ruff configuration |
| [rag-server/requirements.in](../rag-server/requirements.in) / [requirements.lock](../rag-server/requirements.lock) | Direct runtime dependencies and exact production resolution |
| [rag-server/requirements-test.in](../rag-server/requirements-test.in) / [requirements-test.lock](../rag-server/requirements-test.lock) | Direct test dependencies and exact test-only resolution |
| [rag-server/alembic.ini](../rag-server/alembic.ini) / [migrations/env.py](../rag-server/migrations/env.py) / [initial revision](../rag-server/migrations/versions/0001_knowledge.py) | Migration environment, lock and explicit six-table DDL/indexes/model contract |
| [rag-server/tests/](../rag-server/tests/) | PostgreSQL integration, extraction/chunking/model/retrieval, MCP/auth/retry/migration tests and isolated fixtures |
| [rag-server/samples/](../rag-server/samples/) | Illustrative Device A/B issues and device/shared manuals for uploads |

The standalone README maps every `rag/` module; keep that internal ownership description there instead of duplicating it across root specifications.

## RAG integration and tests

| File | Purpose |
| --- | --- |
| [core/src/mcp/network-policy.ts](../core/src/mcp/network-policy.ts) | Shared exact-origin/socket-DNS guarded HTTP adapter for MCP and REST |
| [core/src/rag/rag.module.ts](../core/src/rag/rag.module.ts) | Register RAG integration with the existing MCP registry |
| [core/src/rag/rag.controller.ts](../core/src/rag/rag.controller.ts) | Connection/permission/test/upload routes and strict REST operation allowlist |
| [core/src/rag/rag.service.ts](../core/src/rag/rag.service.ts) | Persist registry profile extensions/token references, independent connectivity and forwarding |
| [core/src/rag/rag-client.ts](../core/src/rag/rag-client.ts) | Reusable bounded authenticated REST client, multipart/204/error normalization |
| [ui/src/types/rag.ts](../ui/src/types/rag.ts) | Verified external knowledge and public connection/search types |
| [ui/src/lib/rag-api.ts](../ui/src/lib/rag-api.ts) | Typed integration calls, multipart upload and bounded complete catalogs |
| [ui/src/components/rag/rag-navigation.tsx](../ui/src/components/rag/rag-navigation.tsx) | Compact independently collapsible sidebar destinations |
| [ui/src/components/rag/rag-workspace.tsx](../ui/src/components/rag/rag-workspace.tsx) | Main-area profiles and management navigation |
| [ui/src/components/rag/connection.tsx](../ui/src/components/rag/connection.tsx) | Separate endpoints/statuses, write-only tokens, discovered tools/permissions |
| [ui/src/components/rag/management.tsx](../ui/src/components/rag/management.tsx) | External device/issue/document CRUD, polling, explicit evidence and retrieval views |
| [ui/src/components/rag/common.tsx](../ui/src/components/rag/common.tsx) | Shared shadcn actions, Radix dialogs, fields, searchable device choices and source passages |
| [ui/vitest.config.ts](../ui/vitest.config.ts) / [ui/tests/setup.ts](../ui/tests/setup.ts) | React/jsdom test configuration and cleanup |
| [ui/tests/navigation.test.tsx](../ui/tests/navigation.test.tsx) | Collapsible RAG navigation/selection |
| [ui/tests/rag.test.tsx](../ui/tests/rag.test.tsx) | Connections, CRUD, uploads, status polling, evidence and retrieval errors |
| [ui/tests/chat.test.tsx](../ui/tests/chat.test.tsx) | Draft/navigation and ordinary chat reply regression |
| [core/tests/rag.test.cjs](../core/tests/rag.test.cjs) | Origin/address/path security, REST/auth/multipart, connection states and Responses tool-loop fixtures |
| [core/tests/environment.test.cjs](../core/tests/environment.test.cjs) | Serialized credential persistence/permissions/conflicts in an isolated temporary .env |
| [core/tests/database.test.cjs](../core/tests/database.test.cjs) | Optional real PostgreSQL idempotent schema/registry/chat/file/retry/source trace checks, test-only DB safeguard |

MCP and RAG screenshots are indexed in UI_SPEC.md; they are review artifacts, not application knowledge. The standalone service file maps remain in their own READMEs.

## Generic MCP UI and manufacturing demonstration

| File or directory | Purpose |
| --- | --- |
| [core/src/mcp/](../core/src/mcp/) | Generic MCP registry, official SDK connection/discovery/execution, URL policy, allowlists and permission checks |
| [core/src/chats/](../core/src/chats/) | Existing-model tool loop, bounded trace summaries, persisted continuation and explicit state-changing call confirmation |
| [ui/src/components/mcp/](../ui/src/components/mcp/) | Compact navigation and main-area generic connection/discovery/permission management |
| [ui/src/lib/mcp-api.ts](../ui/src/lib/mcp-api.ts) / [ui/src/types/mcp.ts](../ui/src/types/mcp.ts) | Typed generic MCP backend API and public UI data contracts |
| [ui/src/components/chat/message-list.tsx](../ui/src/components/chat/message-list.tsx) | Existing chat confirmation cards and bounded tool activity display |
| [manufacturing-demo/README.md](../manufacturing-demo/README.md) | Canonical standalone demo startup, security, REST/MCP use, testing and internal module map |
| [manufacturing-demo/docker-compose.yml](../manufacturing-demo/docker-compose.yml) / [Dockerfile](../manufacturing-demo/Dockerfile) | Independent PostgreSQL and Python ML/MCP service deployment |
| [manufacturing-demo/manufacturing/](../manufacturing-demo/manufacturing/) | Seed, frozen evaluation data, database, dataset queries, model lifecycle, REST and MCP; per-module purposes are in the standalone README |
| [manufacturing-demo/tests/](../manufacturing-demo/tests/) | Isolated PostgreSQL and live HTTP/MCP service tests |
| [verification/manufacturing-agent-*.json](verification/) | Sanitized actual-agent prediction, dataset, metrics and confirmed training traces |

## Chat context management

| File | Purpose |
| --- | --- |
| [core/src/llm/context-window.ts](../core/src/llm/context-window.ts) | Model token capacities, exact provider counting, native model compaction, private context types and sanitized provider requests |
| [core/tests/context.test.cjs](../core/tests/context.test.cjs) | 90% boundary, compaction/carryover/model change, per-prompt budgets, timeout and replay fixtures |
| [core/tests/openai-fixture.cjs](../core/tests/openai-fixture.cjs) | Shared short-context token-count fixture for existing model/confirmation regressions |

Chat persistence and UI continuation coverage extend the existing database/chat tests; no separate context service or frontend is introduced.

[Chat-context verification](verification/chat-context.md) records the executed fixture/database/build/deployment checks and their limits. Its browser screenshots are indexed in UI_SPEC.md.

## Durable tasks

| File | Responsibility |
| --- | --- |
| core/src/tasks/task-contract.ts | Validation, canonical operation identity and deterministic evidence predicates |
| core/src/tasks/tasks.service.ts | Task/checkpoint APIs, approvals, reconciliation, verification and conversation replies |
| core/src/tasks/task-worker.ts | Claims, leases, fences, prompt checkpoints/summaries, retries and operation ledger |
| core/src/tasks/task-context.ts | Atomic delivery fingerprints, bounded incremental model updates and task-owned evidence paging |
| core/src/tasks/execution-policy.ts | Backend MCP grants and structured workspace/command permissions |
| core/src/tasks/task-decision-parser.ts | Bounded extraction of one JSON decision from formatted output, schema and action validation |
| core/src/tasks/task-prompt.ts | Structured decision schema/instructions for the existing saved LLM |
| core/src/tasks/task-schedules.service.ts | Durable cron/one-time schedules |
| core/src/tasks/tasks.controller.ts | REST configuration/control endpoints and SSE |
| core/src/tasks/tasks.module.ts | Existing-core module wiring |
| database/migrations/ | Checksum-protected task persistence/cost/context-checkpoint upgrades |
| ui/src/components/chat/task-feedback.tsx | Live per-message task outcomes and expandable request outputs inside chat |
| ui/src/components/tasks/ | Matching TASKS navigation and management forms/details |
| ui/src/lib/tasks-api.ts; ui/src/types/tasks.ts | Frontend REST client and task contracts |
| docker-compose.tasks-workspace.yml | Optional isolated writable workspace mount |
| core/tests/tasks*.test.cjs; ui/tests/tasks.test.tsx | Policy, persistence/worker and UI tests |
| core/tests/task-restart-* | Real container crash/recovery test fixture and review script |
| docs/TASK_EXECUTION.md | Task runtime/safety/configuration/API and testing specification |

| docs/verification/task-context-checkpoints.json | Actual resumed CNC task, context delivery, migration and verification evidence |

## Active ZSK manufacturing service

`zsk-service/README.md` owns lifecycle, API/MCP, connection, deployment and limits. `zsk/zsk_model.py` reuses supplied classifier/features; `schemas.py` owns units/validation; `db.py` migrations/seed; `service.py` jobs/history/idempotency/model versions; `mcp_server.py` SDK adapters; `api.py` REST/auth/lifespan; `config.py` env; `auth.py` permission scope; `cli.py` entrypoint. `migrations/001_baseline.sql` is supplied schema; 002 adds durable runtime; 003 preserves prediction/job links and source integrity. `data/` contains exact supplied CSVs. Docker/Compose reuse the existing dedicated DB volume and new model volume. `tests/` owns isolated model/DB and live HTTP/MCP checks. `docs/verification/zsk-results.md` records executed checks. Historical manufacturing-demo is superseded at runtime.

## Manufacturing research report

`docs/manufacturing-meta-harness/` owns the current 16-page general-engineer guide (`manufacturing-meta-harness.pdf`, `main.tex`, `guide/`) and the preserved 29-page audit (`technical-report-2026-10-09.pdf`, `technical-report.tex`, original `chapters/` and `figures/`). The short guide uses the actual factory game to explain the line, signals, models, investigation, animation and operator actions, then tells the agent story: LLM connection, execution loop, tools/security, RAG, memory/context and validation/recovery. `guide/build_data.py` verifies exact CSV/recorded-episode plot inputs, matrices, routing examples and copied screenshot provenance; `guide/data-audit.json` records source hashes. `guide/font-setup.tex` selects genuine Calibri for the LuaLaTeX build; licensed font binaries remain in ignored `.build/fonts/` and are excluded from the source archive. All authored text is black. `README.md` owns compilation/provenance and `QA.md` records document checks. Local screenshot/CSV assets plus a licensed Calibri copy support standalone source-archive compilation. The guide explains current limitations without changing application behavior or replacing engineering specifications.

## Autonomous factory extension

- `factory-service/factory/{domain,store,worker,api,mcp_server,config,cli}.py`: external domain authority, persistence, monitoring/outbox, REST/WS/MCP/auth/config/runtime.
- `factory-service/migrations/001_factory.sql`: additive manufacturing checkpoint/action/event/alarm/outbox schema.
- `factory-service/{Dockerfile,docker-compose.yml,docker-compose.test.yml,docker-compose.recovery-tests.yml,.env.example,README.md}`: independent runtime, isolated tests and operator procedures.
- `factory-service/scripts/{configure,demo,recovery_check,browser_check}.py`: explicit local registration/policy, real unattended observation, actual container recovery and rendered UI checks.
- `factory-service/tests/`: clock/signals/forecast/schema/permissions/persistence/MCP/WS/outage regressions.
- `zsk-service/zsk/{synthetic,forecast}.py`, migration `004_forecast.sql`: separate synthetic future-onset baseline with chronological evaluation/trusted artifacts.
- `core/src/integrations/`, `core/config/task-integrations.json`, migration `004_task_integrations.sql`: scoped authenticated template events using existing durable tasks.
- `core/src/factory/`: fixed authenticated browser gateway; `core/src/llm/llm.service.ts`, task prompt/context: strict native decision submission/bounded retry.
- `ui/src/components/factory/`, `ui/src/{lib/factory-api,types/factory}.ts`: original Phaser renderer/navigation/panels and versioned sync.
- Root `docker-compose.factory.yml`, `.env.example`: optional network bridge/scoped configuration.
- `docs/FACTORY_ARCHITECTURE.md`, `docs/verification/factory/`: engineering contracts, actual metrics/screenshots/execution and recovery evidence.
