# Local Operations

Run commands from the repository root. Current service topology and image internals are in [LOCAL_ARCHITECTURE.md](LOCAL_ARCHITECTURE.md).

## Full Docker stack

Requires Docker Engine and Docker Compose:

~~~sh
docker compose up --build -d --wait
docker compose ps
~~~

| Address | Purpose |
| --- | --- |
| http://localhost:8080 | Browser UI |
| http://localhost:8080/api/health | API/database health through the UI proxy |
| http://localhost:8000/api/health | Direct core/database health |

Compose builds meta-harness-ui:local, meta-harness-core:local, and meta-harness-database:local. PostgreSQL is private to the Compose network. Saving/downloading chats works locally; assistant replies and model discovery require internet access to OpenAI.

~~~sh
docker compose logs -f
docker compose down
~~~

Stopping/removing containers retains the message-data volume. Recreating containers or rebuilding images retains chats and attachment bytes. Removing the volume deletes that data; routine shutdown must not remove it.

### Required secret configuration

The root .env is the local source of truth for every password, token, API key, and future confidential connection setting. It is ignored by Git, excluded from Docker build contexts, and restricted to owner read/write permissions (0600). Never publish its contents.

If it does not exist, copy [.env.example](../.env.example) to .env, run chmod 600 .env, and fill DB_PASSWORD locally before starting services. Do not overwrite an existing .env. The committed example deliberately has an empty value, so copying it alone does not create a usable password.

Compose reads .env and explicitly maps DB_PASSWORD to:

- database: POSTGRES_PASSWORD, used to initialize the PostgreSQL user.
- core: DB_PASSWORD, used by the pg connection pool.

Both values are required. There is no hardcoded or fallback password. Native core loads the same root file before Nest module creation using Node's built-in environment-file loader. Its path does not depend on the launch working directory. Container core receives DB_PASSWORD through its environment and has a runtime read/write bind of the root .env at /app/.env for LLM and RAG credential updates. The file is never copied into an image; ui/database do not mount it. Existing shell/process values take precedence.

Only the required database credential is injected into database. Core can read the root .env through its narrow file bind, as needed for the user-authorized key-entry feature. No credentials are passed to ui except the requested four-character key mask. Never give a secret a VITE_ name: Vite exposes those values to browser code. Future profiles must store an environment-variable reference rather than a raw secret; logs, traces, API responses, and browser storage must exclude raw values.

#### Existing database and password changes

An initialized PostgreSQL volume retains its database user's authentication record. Editing DB_PASSWORD in .env changes the application's connection setting, but does not change that user's stored password.

During the .env migration, the existing running core's credential was copied into .env only because DB_PASSWORD was missing. Other local entries and the data volume were preserved. The password value is not recorded in committed source or documentation.

For a future password change, change the database user's password and the root .env together, then recreate services with docker compose up -d --wait. Do not delete the volume to rotate a password. Changes to injected database/general settings require service recreation; native core must restart to reload startup settings. LLM API changes are read from .env immediately and need no restart. If an external editor replaces .env atomically, recreate core to bind the new file inode.

### Public-image credential-helper failure

If a public image pull fails with the observed error “gpg: decryption failed: No secret key”, use a separate empty Docker client configuration:

~~~sh
mkdir -p /tmp/networkagent-docker-config
printf '{"auths":{}}\n' > /tmp/networkagent-docker-config/config.json
docker --config /tmp/networkagent-docker-config compose up --build -d --wait
~~~

This uses anonymous access for public base images and leaves the normal Docker configuration untouched.

## Native development with containerized PostgreSQL

Requires npm and a Node version satisfying the root manifest: Node 22.13+ in the 22.x line, or Node 24+. Docker uses Node 24.

If full-stack containers are running, stop them first to free ports 8080 and 8000:

~~~sh
docker compose down
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d --wait database
npm ci
npm run dev
~~~

The development override exposes PostgreSQL at 127.0.0.1:5432. The root dev command runs NestJS watch mode and Vite concurrently. Open http://localhost:8080.

Run applications separately when needed:

~~~sh
npm run dev --workspace core
npm run dev --workspace ui
~~~

Native core automatically reads DB_PASSWORD from the root .env, using the same credential as Compose; no password export is needed.

## Runtime environment

| Variable | Native core default | Use |
| --- | --- | --- |
| CORE_HOST | 127.0.0.1 | NestJS listening interface; Dockerfile sets 0.0.0.0 inside its container |
| CORE_PORT | 8000 | NestJS port; also read by Vite's native API proxy |
| DB_HOST | 127.0.0.1 | PostgreSQL host; Compose sets database |
| DB_PORT | 5432 | PostgreSQL connection port |
| DB_NAME | meta_harness | Database name; Compose uses this fixed name |
| DB_USER | meta_harness | Database user; Compose uses this fixed name |
| DB_PASSWORD | Required; no default | Secret from root .env, or explicitly injected runtime environment |
| OPENAI_API_KEY | Unset | Secret saved through the LLM form; used only server-side |
| LLM_PROVIDER | openai | Supported LLM provider |
| LLM_MODEL | Unselected | ID selected from the remote OpenAI catalog |
| LLM_THINKING | medium | instant, medium, or high preference |
| LLM_CONTEXT_WINDOW_TOKENS | Model default | Optional exact capacity in root .env. Verified gpt-6-luna/gpt-6.1-sol/gpt-6-astra: 1,050,000; unlisted IDs: conservative 128,000. Valid range 8,192–2,000,000. |
| LOCAL_UID / LOCAL_GID | 1000 / 1000 in Compose | Match the host .env owner's IDs for unprivileged core writes |

The full Compose stack fixes the published ports and Nginx upstream in its files. Setting CORE_PORT in .env does not reconfigure Compose ports or Nginx. For native development, export CORE_PORT before npm run dev so both core and the Vite proxy inherit it. Other non-secret DB connection settings may be supplied in the root .env or shell; passwords and confidential values belong in .env.

Vite dev/preview uses 8080 with strictPort: true. Nginx listens on container port 80. The normal Compose stack does not publish database port 5432.

## Build and code checks

~~~sh
npm run build
npm run typecheck
npm run lint
~~~

Build output is ui/dist and core/dist. Generated dist, node_modules, and TypeScript incremental files are ignored. Root npm test runs UI/core suites; coverage status is in [ACCEPTANCE_TESTS.md](ACCEPTANCE_TESTS.md).

Preview a built frontend with npm run preview --workspace ui while core and PostgreSQL are running. To add a shadcn component, use npx shadcn@latest add <component> --cwd ui.

## Persistence and troubleshooting

- API health checks query PostgreSQL. A failed database connection makes core unhealthy and prevents initial ui startup.
- Native startup needs a running database and nonblank DB_PASSWORD; core loads .env and initializes the schema before listening. A missing required secret stops startup with its variable name, not its value.
- Port-in-use errors usually mean the full Docker UI/core and native servers are running together.
- Browser send/load failures appear in the UI; drafts remain after failed saves. Inspect core logs for server details.
- Upload limits and the current API are specified in [API_SPEC.md](API_SPEC.md).
- There is no authentication or multi-user authorization layer. This is a local application with host ports bound to loopback.

## OpenAI configuration

Expand LLM in the sidebar. Enter a key, choose Save API key, then select a model from the online list and Instant/Medium/High thinking. Save settings persists those preferences. Refresh repeats the server-side catalog request.

The key input clears on submission. Subsequent reads return only the first four characters plus stars. There is no reveal control. Provider/network errors do not echo the key or raw upstream response. Model discovery uses the fixed https://api.openai.com/v1/models endpoint and does not perform paid inference. Model availability depends on the saved key; thinking compatibility varies by model.

LLM updates preserve all other .env entries. Keep the file at mode 0600 and ensure the Compose runtime UID/GID matches its owner (id -u / id -g). On this workstation both are 1000. For a different owner, set LOCAL_UID/LOCAL_GID in .env before recreating core. Do not loosen file permissions to grant access.

The .env bind must point to an existing file (create_host_path is false). Writes are serialized in place, synced, and restored on an ordinary write failure where possible. They are not atomic across a crash/power loss; avoid parallel edits from another process. This is one local core instance, not a multi-instance secret store.

The current feature uses OPENAI_API_KEY; older ANALYZER_API_KEY/ANALYZER_BASE_URL entries are preserved but unused. General ports remain unchanged.

### Chat replies

Sending commits the user message before requesting a reply using the saved model/thinking. Core sends the selected chat's text history, local attachment filenames and explicitly permitted retrieval context to https://api.openai.com/v1/responses. File bytes remain in PostgreSQL. Requests use store:false; enabled read-only RAG tools are offered for model selection, and retrieved evidence is sent to the saved OpenAI model; this is paid OpenAI inference. Provider retention policies still apply; store:false is not a zero-retention guarantee.

Instant maps to reasoning effort none; Medium/High map directly. Model availability does not guarantee Responses or effort support. Unsupported combinations fail visibly; select a compatible text/reasoning model rather than expecting automatic substitution.

Each prompt has a two-minute deadline, eight model turns and twelve tool calls. At a budget boundary the UI automatically starts the next prompt from saved work; Nginx permits 150 seconds for each HTTP request. Twenty automatic continuations per UI run or three consecutive deadline prompts without model/tool progress pause for retry. Authentication/quota/ordinary network errors remain visible. Confirmations still require the user. Responses appear after completion without streaming. Reopening an interrupted chat offers Retry response; saved tool results prevent replay. An interrupted provider request may still be billed, and automatic continuation can incur another charge.

Core counts rendered input, including tool schemas, before inference and asks the selected model to compact it at 90% of its configured capacity. The complete returned window persists in PostgreSQL while the visible transcript remains intact. Its summary is opaque model memory and can lose details. Output is bounded to 8,192 tokens or 8% of the configured capacity, whichever is smaller; private context/checkpoints have a separate 16 MiB safety limit. The model-list API does not return context sizes: for an unlisted model, set `LLM_CONTEXT_WINDOW_TOKENS` to its documented capacity, especially if smaller than the fallback. Root .env is reread each prompt. Unsupported counting/compaction, ineffective summaries and oversized input fail clearly. A model change rebuilds context from the saved transcript.

### Recorded image-build fallback

During the 2026-10-09 configuration update, Docker Hub timed out resolving public base images. Native workspace builds and lint completed; compiled outputs were packaged on top of the existing local Node/Nginx application runtime images using temporary build contexts with no .env. The inference update used the same cached-runtime procedure and refreshed the schema in both core and the local PostgreSQL image. Dependencies and runtime base versions were unchanged. The committed Dockerfiles remain the normal reproducible build recipes for subsequent builds when the registry is reachable.

## MCP connections and standalone RAG

Root `.env` additionally holds `RAG_DB_PASSWORD`, `RAG_API_KEY`, and any generic `MCP_*` bearer tokens. Core reads credential references from that file on each discovery; no restart is needed after an in-place edit. Atomically replacing the bind-mounted file still requires recreating core. RAG containers receive their own secrets through Compose environment; recreate them after changing injected settings. Do not overwrite existing secrets/passwords or print resolved Compose configuration.

Start the independent retrieval stack from `rag-server/` using `docker compose --env-file ../.env up -d --build`. It runs at loopback 8090 with a private PostgreSQL/pgvector and persistent original/model volumes. Its [README](../rag-server/README.md) owns all RAG configuration, curl upload/search examples, tests and troubleshooting.

To connect containerized core, create `meta-harness-mcp` once, then from root run `docker compose -f docker-compose.yml -f docker-compose.mcp.yml up -d --build`; from `rag-server/` run `docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.meta-harness.yml up -d --build`. Always include both bridge files on subsequent recreations if the connection should remain reachable.

In the UI, expand **RAG → Connection**, select the existing Local RAG profile (or New), set a name, separate **MCP URL http://rag-api:8090/mcp** and **REST API URL http://rag-api:8090**, and None/Bearer authentication. Existing root RAG_API_KEY references are reused; new/replacement tokens entered here are saved write-only as generated MCP_TOKEN_<UUID> entries in root .env. Token inputs clear after submission and there is no reveal control. If testing an unsaved token, reenter it when saving.

Click **Save Connection**, then **Test Connection** to verify the saved endpoints. Check MCP and REST statuses independently. Select trusted discovered read-only retrieval tools, tick **Make allowed retrieval tools available to chat**, and **Save tool permissions**. MCP retrieval can work when REST fails; management can work when MCP fails. Saving resets tests and disables chat use; Disconnect retains settings and revokes calls. Retest reconnects a disconnected saved profile. Management links open in the main area; **Back to chat** restores the composer/draft.

Native core uses MCP **http://127.0.0.1:8090/mcp** and REST **http://127.0.0.1:8090**. Container localhost addresses refer to core itself, so use the shared Docker alias for this deployment. Other servers require the operator to add their exact origin (scheme, host, port) to root **RAG_ALLOWED_ORIGINS**. Default origins are http://rag-api:8090,http://rag:8090,http://localhost:8090,http://127.0.0.1:8090. This non-secret setting is read live from the shared environment store. URL credentials/query/fragment, redirects, cross-origin MCP requests and metadata/link-local addresses are rejected. No wildcard or arbitrary proxy exists.

Use **Devices**, **Known Issues**, **Documents** and **Knowledge Search** for external knowledge. Device model/manufacturer and issue category/symptoms are required by the actual server. Document descriptions are metadata.description; multi-device associations are explicit. Pending statuses poll without invented percentages; Refresh retries after network failure. Original file download is unavailable in the current server. Core catalog views load complete datasets up to 5,000 records and show an error beyond the cap.

## Integration tests

`npm test` runs Vitest component tests and core Node/official SDK fixtures. Core's real PostgreSQL regression test additionally uses **CORE_TEST_DATABASE_URL**; it refuses database names not ending in _test/_tests and otherwise skips when unset. Use an isolated disposable database; never point it at chat/knowledge data. It checks idempotent upgrades, registry create/update, messages/files, title generation, source traces and reply retries. The real RAG suite remains separate and was not rerun/modified for this integration. Ordered workflow/validator acceptance remains future work.

## Manufacturing ML/MCP demonstration

This separate optional stack is documented in [`manufacturing-demo/README.md`](../manufacturing-demo/README.md). Set its two `MANUFACTURING_*` secret values in root `.env`; then run from `manufacturing-demo/` with `docker compose --env-file ../.env up -d --build --wait`. The API is published only on loopback port 8100; PostgreSQL remains private. For disposable service tests use `docker compose --env-file ../.env -f docker-compose.test.yml up --build --abort-on-container-exit`. Core must share `meta-harness-mcp`; containerized core connects to `http://manufacturing-ml:8000/mcp`, native core to `http://127.0.0.1:8100/mcp`. Add only the configured URL's exact origin to `MCP_ALLOWED_ORIGINS` when it is not already allowed. The service is synthetic, has no generative LLM, and never changes ground-truth labels. `GET /health` is liveness; protected `GET /ready` checks database/model availability.

## Task operations

Core runs the task worker and scheduler by default. Apply/rebuild through the existing Compose stack; migrations run automatically under a transaction lock. Root .env owns all TASK_* settings. Task turn/token/active-time budgets apply per prompt; checkpoints automatically continue up to TASK_MAX_CONTINUATIONS, while lifetime accounting and optional cost caps persist. Optional local files: `mkdir -p task-workspace`, then add `-f docker-compose.tasks-workspace.yml` to Compose. No host Docker socket is mounted. See [TASK_EXECUTION.md](TASK_EXECUTION.md) for limits, schedules, approvals, safe reconciliation and isolated restart tests.

## Current ZSK manufacturing deployment

The old manufacturing startup above is superseded. Use `cd zsk-service` then `docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.meta-harness.yml up -d --build --wait`. Never start the old manufacturing database concurrently: both configurations reference the same dedicated data volume. Current secrets are ZSK_API_KEY (read-only), ZSK_ADMIN_API_KEY (writes), and existing MANUFACTURING_DB_PASSWORD in root .env. Port/compatibility bridge URL stay 8100 / http://manufacturing-ml:8000/mcp. Current lifecycle purges labeled training data after successful model activation; restart does not restore it. See ../zsk-service/README.md for interfaces, new-install volume creation and tests.

## Optional factory service

[factory-service/README.md](../factory-service/README.md) owns exact startup/registration/demo/test commands. Start the updated ZSK service **with its meta-harness bridge overlay** before building factory; otherwise alias `manufacturing-ml` is unavailable. Use root optional factory overlay to give core its bridge alias. Runtime host bindings remain loopback; factory adds 8110 and UI stays 8080.

Root-only secrets: `FACTORY_API_TOKEN` (core→operator REST/WS), `FACTORY_MCP_AUTH_TOKEN` (generic MCP), `TASK_INTEGRATION_TOKEN` (limited event templates), `FACTORY_TEST_DB_PASSWORD` (isolated tests). Existing `ZSK_API_KEY`/`MANUFACTURING_DB_PASSWORD` are reused, never replaced. Non-secret profile IDs/RAG asset UUID/policy/configuration also persist in root `.env`; examples contain empty secret values. Factory Compose injects only required credentials; ui/database never receive the root file. No database host port is added to runtime.

Automatic simulated stop/restart/maintenance default false. Operator-run `configure.py --demo-stop` is the explicit requested demonstration stop authorization; restart/maintenance remain false. Recreate core/factory after config writes. Arbitrary event requests/tool grants cannot be supplied by the service token. Factory runs continuously without an open browser; downtime freezes simulated time. Restart/task/outbox evidence is under `docs/verification/factory/`.
