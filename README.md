# Local Meta-Harness

A local Meta-Harness chat application with a generic MCP registry and an optional standalone manufacturing ML demonstration.

**Current:** saved conversations, OpenAI responses, external RAG management, and configurable MCP connections with discovered, operator-allowed tools. Read-only tools can run directly; other chat tools require per-invocation user confirmation. Persistent tasks add backend continuation, verification, retries, schedules, and TASKS management. The frontend uses React, TypeScript, Vite, Tailwind CSS, and shadcn/ui; the backend uses NestJS and TypeScript.

## Start the local stack

Requires Docker Engine and Docker Compose. The root ignored .env must contain DB_PASSWORD. If no .env exists, copy [.env.example](.env.example) and set the password locally before startup; preserve existing entries and the password of an initialized database volume. Native core also loads this same file.

From the repository root:

~~~sh
docker compose up --build -d --wait
~~~

Open [the UI](http://localhost:8080). The API is available on [port 8000](http://localhost:8000/api/health). PostgreSQL stays inside the Compose network; its data uses the persistent message-data volume.

Use **New chat**, type a message or attach files with **+**, then press **Send**. Saved titles appear under **Chats**; click its heading or chevron to collapse/expand the list. Enter sends; Shift+Enter inserts a newline. File cards in saved messages download the attachment.

## Documentation

| File | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Engineering instructions and fixed product boundary |
| [Project map](docs/PROJECT_MAP.md) | Purpose of every maintained file |
| [Architecture](docs/LOCAL_ARCHITECTURE.md) | Current frameworks, modules, service flow, images, and ports |
| [Operations](docs/OPERATIONS.md) | Docker/native startup, environment settings, logs, and persistence |
| [UI specification](docs/UI_SPEC.md) | Current appearance, controls, and responsive behavior |
| [Data models](docs/DATA_MODELS.md) | PostgreSQL tables and storage rules |
| [API specification](docs/API_SPEC.md) | Implemented routes, requests, responses, and errors |
| [Implementation decisions](docs/IMPLEMENTATION_DECISIONS.md) | Current structural choices and their reasons |
| [Acceptance checks](docs/ACCEPTANCE_TESTS.md) | Recorded validation and current coverage gaps |
| [Roadmap](docs/ROADMAP.md) | Future work and product boundary |
| [MCP contracts](docs/MCP_CONTRACTS.md) | MCP registration, permissions, confirmation, and tool-call behavior |
| [Manufacturing demo](manufacturing-demo/README.md) | Independent synthetic-data ML service, Docker, REST, MCP, and tests |

Expand **LLM** in the sidebar to configure OpenAI. Expand **MCP** to register servers, discover tools, and choose permissions. Server credentials stay in root `.env`; only environment-variable references are stored in MCP profiles. The optional [manufacturing demo](manufacturing-demo/README.md) exposes a seeded synthetic classifier and MCP service on port 8100. The separately deployed RAG service remains an external retrieval system.

## Standalone RAG and MCP configuration

[rag-server/README.md](rag-server/README.md) owns the complete independent FastAPI/PostgreSQL+pgvector service, local models, six-table schema, REST/MCP APIs, Docker startup, sample uploads and pytest instructions. It has no frontend or answer generation. REST/OpenAPI runs at [localhost:8090/docs](http://localhost:8090/docs). Secrets are `RAG_DB_PASSWORD` and `RAG_API_KEY` in root `.env`; preserve other entries.

To bridge the two local stacks, create the `meta-harness-mcp` Docker network once, start core using `docker compose -f docker-compose.yml -f docker-compose.mcp.yml up -d --build`, and start RAG from its directory with `docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.meta-harness.yml up -d --build`.

In **RAG → Connection**, select **Local RAG** (or create a profile), enter **MCP http://rag-api:8090/mcp** and **REST http://rag-api:8090**, and choose authentication. The existing RAG_API_KEY reference is retained; new tokens are entered once and saved server-side in root .env. **Save Connection**, **Test Connection**, select the discovered read-only retrieval tools, enable their use in chat, then **Save tool permissions**. Open Devices/Known Issues/Documents/Knowledge Search to manage external knowledge. **Back to chat** restores your draft. The saved model decides when retrieval is useful. See [operations](docs/OPERATIONS.md) for credential/network details.

UI/core checks: `npm test`; optional real PostgreSQL checks use CORE_TEST_DATABASE_URL as described in operations. Standalone tests run with its dedicated Docker test Compose file; see its README.

## Persistent tasks

Select **Run as task** in chat, or open **TASKS → Active Tasks → New task**. Core continues independently of the browser and recovers unfinished tasks after restart. Review pending actions and real verification evidence in Task details. Task requests remain in chat with live outcomes and a link to details. Configure schedules in the sidebar; event triggers are temporarily removed. See [task execution](docs/TASK_EXECUTION.md) for configuration, APIs, safety boundaries, migration and test instructions.

### Active manufacturing service: ZSK

The previous manufacturing example has been replaced at runtime by [ZSK condition monitoring](zsk-service/README.md), using the supplied RandomForest model and timestamped synthetic data. It reuses the manufacturing database, trains on labeled data, then removes those rows and serves unlabeled measurements/predictions. Host port 8100 and existing generic MCP UI are retained. Old manufacturing-demo startup instructions are historical; use the ZSK README.

## Autonomous factory simulation

The optional **FACTORY** section at `http://127.0.0.1:8080` provides an original animated 2D ZSK-style extrusion line, real persisted synthetic sensors, current/future ML monitoring, alarms, automatically triggered persistent investigations, RAG evidence and authorized simulation-only MCP actions. Factory backend is loopback 8110; existing application ports/layout remain unchanged. No physical equipment control exists.

See [factory-service/README.md](factory-service/README.md) for complete startup, MCP registration, speed/fault/permission configuration, automatic demonstration and isolated tests. [FACTORY_ARCHITECTURE.md](docs/FACTORY_ARCHITECTURE.md) explains source mechanisms and limitations. Screenshots/model/recovery/live-run evidence live in `docs/verification/factory/`. All measurements and model performance remain synthetic proofs of concept.
