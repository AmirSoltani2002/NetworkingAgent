# Current Implementation Decisions

These records describe the current structure as of 2026-10-09. Superseded static-HTML, Python, and browser-only-storage choices have been removed. Product boundaries live in [AGENTS.md](../AGENTS.md); future requirements live in [ROADMAP.md](ROADMAP.md).

## 1. User-selected stack

**Decision:** React/TypeScript with Vite, Tailwind CSS, and shadcn/ui for ui; NestJS/TypeScript with its Express adapter for core.

**Reason:** The user selected Vite/shadcn and NestJS. React supports the selected UI component library. Existing source remains separated by component and Nest module.

**Files:** ui/package.json, ui/components.json, ui/vite.config.ts, core/package.json, core/nest-cli.json.

## 2. One npm workspace repository

**Decision:** Keep ui and core as workspaces with one root manifest and package-lock.json. Shared TypeScript, lint, Nest CLI, and concurrent-development tooling live at the root.

**Reason:** One dependency lock and root commands simplify coordinated development and reproducible Docker installs without adding another build-system layer.

**Files:** package.json, package-lock.json, eslint.config.mjs, application tsconfig files.

## 3. UI state and component structure

**Decision:** Use React hooks in App/Composer, a small fetch API module, shared chat types, and focused chat components. Keep shadcn primitives separate from reference-specific CSS and SVG controls.

**Reason:** The current screen needs no global state library. Explicit components preserve the screenshot-matched layout and make individual controls maintainable. Unsaved drafts stay in memory; persisted history comes from core.

**Files:** ui/src/App.tsx, ui/src/components/, ui/src/lib/, ui/src/types/chat.ts, ui/src/chat.css, ui/src/index.css.

## 4. PostgreSQL and direct SQL

**Decision:** Store chat metadata, ordered messages, and attachment bytes in PostgreSQL 17. Use pg with parameterized queries and transactions instead of an ORM or object-storage service.

**Reason:** The user requested a separate database image and persistence. Keeping files and message records together preserves downloads after restarts and makes a save atomic. Existing limits keep this simple local storage choice bounded.

**Files:** database/schema.sql, core/src/database/, core/src/chats/chats.service.ts.

**Limit:** Startup uses idempotent schema initialization, not versioned migrations. Existing-schema changes will need explicit migration work.

## 5. Automatic titles and retry identity

**Decision:** Generate a title from the first saved message or first uploaded filename; collapse message whitespace and cap it at 48 Unicode code points with an ellipsis. Keep later titles unchanged. Use a client UUID as each message's primary key; retries return the original saved message.

**Reason:** Titles work without an external analyzer. A stable submission key prevents duplicate messages after uncertain network failures. Chat-row locking and one transaction keep first-message title assignment and saves consistent.

**Files:** core/src/chats/chats.service.ts, ui/src/components/chat/composer.tsx, ui/src/App.tsx.

**Limit:** New chat creates its database row before the first upload; a failed upload can leave an empty New chat row. Retry keys do not edit existing messages.

## 6. Three local container images

**Decision:** Use a multistage Vite-to-Nginx image, a multistage NestJS Node 24 image with production dependencies/non-root runtime, and a PostgreSQL 17 Alpine image with the schema initializer. Compose provides health-gated startup and a named message-data volume.

**Reason:** The user requested separate frontend, backend, and database images with one local Compose stack. Nginx serves static assets and gives browser API calls one origin; core/database remain independently packaged.

**Files:** ui/Dockerfile, ui/nginx.conf, core/Dockerfile, database/Dockerfile, docker-compose.yml, .dockerignore.

## 7. Ports and native development

**Decision:** Publish UI at 127.0.0.1:8080 and core at 127.0.0.1:8000. Keep PostgreSQL private in the full stack; a minimal Compose override exposes 127.0.0.1:5432 for native development. Vite proxies /api to native core.

**Reason:** Loopback bindings match the local-only phase. Native watch mode can reuse the same database without adding another database process.

**Files:** docker-compose*.yml, ui/vite.config.ts, core/src/main.ts, core/Dockerfile.

## 8. API limits and errors

**Decision:** Validate UUIDs and multipart/text/file limits in core, mirror attachment limits in the composer, sanitize download filenames, return file bytes as attachments, and use a common core error envelope. Preserve unsent drafts on errors. Database access requires a configured environment password, with no fallback credential.

**Reason:** Validation belongs at the persistence boundary. Upload/download behavior stays predictable, and request failures are visible without exposing internal database details to users.

**Files:** core/src/chats/chats.controller.ts, core/src/chats/chats.service.ts, core/src/http-exception.filter.ts, ui/src/components/chat/composer.tsx.

**Limit:** There is no authentication/multi-user authorization yet; the app is for local use.

## 9. Current versus future documentation

**Decision:** Current architecture, UI, schema, API, operations, and checks have separate canonical documents. Consolidate unimplemented product requirements in ROADMAP.md and external tool rules in MCP_CONTRACTS.md. Replace the duplicate implementation task/change log with PROJECT_MAP.md; remove completed plans, duplicate captures, and the unrelated BGP-specific skill. Generalize the optional reviewer instructions.

**Reason:** Documents must describe what exists and avoid implying that planned MCP features or removed implementations are running. A file map explains ownership without duplicating specifications.

**Files:** AGENTS.md, README.md, docs/, .env.example, .gitignore, .dockerignore, .agent/PLANS.md, .codex/agents/reviewer.toml.

## 10. Screenshot-based UI review

**Decision:** Capture and inspect the running UI against the user's reference for every UI change, including desktop and mobile states.

**Reason:** The user explicitly requested visual comparison and iteration, along with functional Send/file controls and removal of unused buttons.

**Files:** AGENTS.md, docs/UI_SPEC.md, docs/ACCEPTANCE_TESTS.md, docs/screenshots/.

## 11. One local secret file, required credentials

**Decision:** Use the root ignored .env for every password and future confidential connection value. Load it with Node's built-in loadEnvFile before native Nest startup; keep container injection explicit in Compose. Require a nonempty DB_PASSWORD in Compose and a nonblank value in core; remove all fallback passwords. Keep .env.example values empty, exclude secrets from Git/images/UI, and restrict the local file to its owner.

**Reason:** The user requested .env as the central local source for current/future confidential configuration. Node's existing loader avoids another dependency and resolves the file consistently for root/workspace launch commands.

**Files:** .env (local, untracked), .env.example, docker-compose.yml, core/src/config/environment.ts, core/src/main.ts, core/src/database/database.service.ts, AGENTS.md, related specifications.

**Compatibility:** Preserved the running database's existing credential when adding DB_PASSWORD to .env; retained other local entries and the data volume. An initialized PostgreSQL user's password is not changed by editing .env alone. Standard process/Compose environment overrides still take precedence.

**Future rule:** Persist environment-variable references in connection profiles, never raw passwords/tokens. Resolve and redact values server-side. Non-secret general structure/settings remain documented in their owning files.

## 12. Collapsible Chats section

**Decision:** Make the Chats heading a shadcn Button with a chevron and independent React open state, expanded by default. Hide the saved-title list and empty-state message when closed; preserve the heading, selected conversation, and draft. Use aria-expanded/aria-controls and native button keyboard behavior.

**Reason:** The user requested a Chats section with its own close/open toggle. Keeping this state inside Sidebar separates section visibility from full-sidebar visibility without adding persistence or dependencies.

**Files:** ui/src/components/chat/sidebar.tsx, ui/src/components/chat/icon.tsx, ui/src/chat.css, related UI/architecture/file-map documentation.

## 13. OpenAI settings and live model catalog

**Decision:** Add a collapsible LLM sidebar form and dedicated Nest LlmModule. Save OPENAI_API_KEY, LLM_PROVIDER, LLM_MODEL, and LLM_THINKING in .env. Clear the key input on submission; read APIs return only four visible characters and stars. Use server-side fetch to the fixed OpenAI models endpoint, with timeout/no redirects and sanitized errors. Return the full available-ID catalog rather than a stale hardcoded list; recheck selected-model availability on save.

**Reason:** The user explicitly requested OpenAI-only company selection, online model discovery, Instant/Medium/High preferences, and .env storage with partial masking. Native Node fetch/environment parsing avoid additional dependencies.

**Runtime choice:** Bind only the existing root .env read/write into core; keep it excluded from builds and ui/database. Match the host owner through LOCAL_UID/LOCAL_GID (defaults 1000). Serialized, allowlisted, synced in-place updates preserve other entries and attempt rollback. File binds cannot be atomically renamed; external atomic edits require core recreation. No database schema change.

**Safety:** JSON-only settings writes reject foreign browser origins, unknown fields, and concurrent API-key changes. Key/provider error bodies are never returned or logged; no full-key retrieval/reveal feature. The required user mask reveals only four characters.

**Limit:** Configuration/model listing performs no inference. The models endpoint returns basic IDs, not endpoint/reasoning capability guarantees. Chat inference (decision 14) sends the selected effort and fails visibly on unsupported combinations rather than silently changing the choice.

**Files:** core/src/llm/, core/src/config/, ui/src/components/llm/, ui/src/types/llm.ts, ui/src/lib/api.ts, sidebar/styles, Compose, .env.example, related documents.

**Official sources:** [Models list](https://developers.openai.com/api/reference/resources/models/methods/list), [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning). No key values or static catalog snapshots are committed.

## 14. Ordinary OpenAI text replies

**Decision:** Persist the user first, clear the composer, and explicitly call a separate response route. LlmService snapshots saved .env settings and submits the selected chat's ordered text history to the fixed Responses endpoint using native fetch, store:false, no tools, and no automatic paid retries. Instant maps to none, Medium/High directly. Incompatible models/efforts fail visibly. Only completed text/refusal responses become assistant messages; plain text rendering preserves the reference and avoids executing generated markup.

**Reason:** The user requested replies from their saved model. Keeping saving separate from generation preserves the message after failures and exposes progress/retry without a workflow engine, new dependencies, or cloud persistence.

**Persistence/concurrency:** Add nullable reply_to_message_id and a unique partial index through idempotent schema.sql statements that upgrade existing volumes. A per-chat PostgreSQL advisory session lock covers generation; saves acquire its matching transaction lock. No SQL transaction runs across the provider request. Existing saved replies return without inference; new generation requires the latest unanswered user. Assistant insert/activity update commit together. Navigation pauses during generation; reopening unanswered history offers explicit retry.

**Limits:** Two-minute provider timeout, 150-second proxy timeout, 1 MiB serialized text-history cap, 8,192 output tokens including reasoning, and no silent history truncation. Responses appear after completion, without token streaming. File bytes remain local; input includes only filenames with an explicit contents-unavailable note, and the composer explains this. No Markdown rendering, reasoning-state/provider-conversation persistence, file analysis, RAG, MCP tools, or execution trace was added. store:false does not guarantee zero provider retention. A timeout/crash before reply commit may require another billed request; database idempotency does not guarantee exactly-once billing.

**Safety:** Keys remain server-side, provider errors become fixed messages, and response/configuration writes reject foreign browser origins using a shared helper. No user key or configuration was changed for review.

**Files:** core/src/chats/, core/src/llm/, core/src/config/local-origin.ts, database/schema.sql, ui/src/App.tsx, message-list/composer, chat types/API/styles, ui/nginx.conf, owning specifications.

**Official sources:** [Responses creation](https://developers.openai.com/api/reference/python/resources/responses/methods/create), [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning), [saved-model effort support](https://developers.openai.com/api/docs/models/gpt-6-luna).

## 2026-10-09 — Standalone RAG and generic MCP settings

- The user explicitly authorized implementing an external RAG server, superseding the previous restriction for this service only. `rag-server/` keeps Python dependencies, six domain tables/Alembic, pgvector database, Docker image and tests independent of the NestJS/React chat app. Core stores connection metadata only; no retrieval internals or generator were added to core.
- Durable ingestion reuses document statuses and reserved JSONB metadata with PostgreSQL advisory locks. API commits uploads promptly; the same-image worker performs extraction/chunking/embeddings, bounded retries/crash recovery and atomic replacement. This avoids extra domain tables, Redis or unnecessary services. File/database operations use compensation plus orphan/quarantine sweeping; backups require both volumes.
- Pinned immutable local sentence-transformer revision/dimension/normalization is a database contract. Schema comments avoid a seventh domain configuration table; chunks also carry model/version metadata. Structure detection and safety/procedure protection precede semantic chunking; token limits force explicitly marked fragments. No OCR or generative splitter is introduced.
- Retrieval always includes independent direct document search. SQL applicability filters, vector/English FTS candidates, known issues/explicit evidence, RRF deduplication and optional pinned local cross-encoder return evidence, not diagnosis or calibrated confidence. Reprocessing replaces UUID chunks and cascades old explicit links; links must be recreated intentionally. Issue moves/document applicability changes prune incompatible evidence transactionally, with row locks shared by link insertion.
- Python MCP 1.x stateless Streamable HTTP shares REST services and enforces bearer auth/Host allowlists. Non-root application/worker image and persistent model/doc/database volumes support local Docker deployment; test Compose isolates destructive migration/cleanup checks from knowledge data.
- Core uses official TypeScript MCP SDK with bounded discovery, credential references resolved from root `.env`, sanitized failures/metadata and explicit read-only tool selections. No auto-execution, shell/stdio runner, workflow, analyzer integration or chat RAG call is added. The shared environment store has one global provider so LLM updates remain serialized.
- Optional shared Docker network connects only core and external RAG API. Default standalone deployment retains its private three-container topology; no frontend container belongs to RAG.

## 2026-10-09 — Existing-app RAG management and model-selected retrieval

This supersedes the earlier MCP-sidebar/no-tool chat scope above. The external RAG implementation is left unchanged. The user requested integration into the existing application, so NestJS remains the backend (not a new FastAPI service). Existing MCP registry, environment store and saved-model Responses path are reused; no separate registry, agent, LLM or knowledge database is introduced.

- Replace MCP sidebar form with compact collapsible RAG navigation/main-area forms. Keep the chat subtree mounted and hidden during management navigation to preserve unsent text/files. Radix provides accessible dialogs; shadcn buttons and reference dark styles remain.
- Extend existing mcp_servers with REST status/config and opt-in chat permissions. New token values go to generated root .env entries, never SQL/browser persistence. Separate save/test avoids marking edited drafts as healthy saved connections. Shared serialized writes preserve unrelated secrets; file write and SQL update cannot be a cross-store atomic transaction, so old credential entries are not automatically deleted.
- Exact operator-approved origins plus actual socket DNS validation/no redirects/cross-origin requests protect the backend from arbitrary SSRF. Local Docker/loopback origins have explicit defaults; metadata/link-local/reserved addresses remain blocked. Untrusted regex tool schemas are rejected instead of evaluated.
- Reuse official MCP SDK and dynamically discovered schemas. Existing model selects permitted generic functions, sequentially, with bounded rounds/time/output and permission revalidation. Carry Responses output/opaque reasoning items between tool turns, but do not persist reasoning/provider state. Fixed errors let the model report unavailable retrieval; source metadata is separate from the generated answer. No mandatory tool call for every message.
- Compact message traces preserve server/tool/success/timing/source references, including calls before a failed provider response, without logging arguments/passages/credentials. Immutable workflow history remains unimplemented.
- Verified actual RAG source/API contracts require model/manufacturer/category/symptoms; forms reflect them. REST operations are allowlisted, normalize 204/errors, and handle multipart. Core stores no knowledge. Document descriptions use metadata.description; original downloads are not invented.
- Current RAG catalogs lack some search/sort/count endpoints. Load complete remote catalogs with a 5,000-record limit for honest local search/filter/sort/pagination/counts; exceed it visibly rather than silently show partial results. Processing polls real statuses every three seconds and pauses after network failure.
- Real database/browser checks caught SQL parameter-type inference and unintended form submission by a test button. Explicit PostgreSQL casts and button types were added with regression coverage, alongside UI/SDK/provider tests. Paid live chat review uses the unchanged saved model and removes only its fixture knowledge/chat afterward.

## 16. Generic MCP management, agent tools and manufacturing demonstration

**Decision:** Extend the current `mcp_servers` registry and saved Responses tool loop. Show generic server management in a compact collapsible MCP section. Discover schemas from the actual server, store only credential environment-variable references, require explicit per-tool permission, and let the existing model choose permitted tools. Require an exact expiring single-use UI confirmation before state-changing calls. Persist only bounded continuation and executed results needed for reload/provider retry; never auto-replay a call whose execution was interrupted. Keep trace summaries bounded and keep workflow scheduling out of this change.

**Reason:** The request was to integrate arbitrary external MCP servers into the existing chat agent and demonstrate one manufacturing ML endpoint. Generic registration avoids service-specific coupling; confirmation supplies a visible authorization step before external writes/retraining. Reusing persisted chats/registry avoids competing storage and agents.

**Demo boundary:** `manufacturing-demo/` owns synthetic data, PostgreSQL, a frozen holdout, scikit-learn model and its REST/MCP service in two containers. The service contains no generative LLM and does not mutate ground truth. Its host port 8100 and bridge URL `manufacturing-ml:8000` are documented in its README. The completed training trace returned evaluation metrics through `get_training_status`; no redundant second metrics tool invocation is required.

## 2026-10-09 — Context compaction and automatic prompt continuation

**Decision:** Count actual Responses input tokens, including tools/instructions. At 90% of the configured capacity, use the same selected model through OpenAI's native compaction endpoint. Carry its complete returned window unchanged, including opaque summary/retained messages. Commit the private window and message-position watermark with the final assistant reply. Keep the visible transcript intact and rebuild it for model changes. Verified current model capacities have defaults; an optional root .env override supports other models. The model-list API does not supply capacities.

**Reason:** Native compaction preserves provider reasoning/tool state without constructing an incomplete function-call history or promoting a generated text summary to a privileged instruction. Exact provider counting avoids character-based token guesses. The opaque summary is lossy and not a readable document.

**Continuation:** Eight model turns, twelve tool calls and two minutes are now per-prompt budgets. Persist a checkpoint and let React request the next prompt automatically. This keeps each HTTP request within the existing proxy timeout. Executed tools are never replayed and state-changing calls still require exact confirmation. Twenty automatic continuations per UI run and three consecutive deadline prompts without progress prevent endless retries. Ordinary errors require explicit retry. Native compaction/provider retries may incur API cost; exactly-once billing is not claimed.

## Durable task execution (2026-10-09)

Extend existing core/LLM/MCP modules rather than introducing an agent framework, queue service or database. Use PostgreSQL row claims plus session locks and lease-owner fences. Persist structured decisions and operation state before external dispatch, reuse completed writes, and pause uncertain writes instead of claiming exactly-once delivery. Freeze model-proposed completion predicates and evaluate them against stored successful outputs. An authenticated durable event inbox and transactional schedule occurrences prevent duplicate tasks. Keep local execution structured and bounded; isolate its optional workspace without exposing the host Docker socket. Runtime details are canonical in TASK_EXECUTION.md.

## Chat-first task feedback and temporary trigger removal (2026-10-09)

Task submission keeps the conversation visible. Per-message task IDs restore readable live outcomes and request outputs after reload; details open only on user navigation. Failure/approval/clarification states remain truthful and do not fabricate completion. Redacted bounded model output events aid diagnosis; malformed structured decisions use the existing bounded retry mechanism. Event-trigger UI, HTTP intake/configuration, dispatch, and completion publication are removed temporarily. Historical tables and applied migrations are retained to avoid destructive history loss. Scheduling remains available.

## Automatic task scope and direct responses (2026-10-09)

Vague/incomplete objectives now use bounded prior conversation context plus currently permitted tool metadata to infer a useful conservative scope and state assumptions. The existing saved model can return a direct respond decision when tools are unnecessary/unavailable. Fresh response-only tasks persist and verify text delivery through an internal read-only response operation, explicitly not verification of external action. Existing external criteria cannot be replaced by response delivery; a best-effort answer is shown while unmet criteria leave the task paused. Tool allowlists, write approvals, replay protection and limits remain enforced.

## Formatted task decision handling (2026-10-09)

Provider output can contain an explanation before the requested structured decision. The task parser now extracts a single JSON object using brace/string/escape state, then validates the full task schema, nested serialized JSON and existing action constraints. It does not repair malformed syntax, evaluate code, or select among conflicting decisions. Ambiguous/invalid output retries before dispatch. Original redacted explanation/output remains visible in chat. No new model, tool permission or database schema is introduced.

During the resumed ML task, tool calls succeeded but a model filter used `{limit:25,offset:0}` property names instead of JSON-pointer keys. Exact property names now receive pointer-token normalization during evidence matching, preserving equality and frozen criteria. A retry may finalize a saved completion decision only after all persisted evidence passes deterministic verification; completed external operations are not replayed.

## Read-only MCP request correction (2026-10-09)

A RAG search rejected a human-readable device name in an ID field. Read-only tool-level errors now return saved error evidence to the existing planner for bounded correction instead of immediately failing or blindly replaying the same invocation. Failed steps/operations remain persisted and cannot satisfy completion checks. Unknown writes still pause for reconciliation, and authentication/permission gates remain enforced. Legacy retry clears rejected read-only next actions so the same malformed parameters are not automatically replayed.

The model also emitted duplicate execute objects differing only in step/summary wording. These are collapsed using canonical identity of every other field; differing actions, arguments, criteria, timing or goals remain rejected. Non-execution answers retain their full identity, including response text. Model-format diagnostics are supplied to subsequent planning turns.

Retry/control status updates explicitly type the shared SQL parameter as text to avoid PostgreSQL inferring incompatible varchar/text types when also evaluating the pending-state CASE expression. Runtime evidence of recovery remains subject to the configured task token budget; limits are not silently reset or bypassed.

## Durable task context checkpoints (2026-10-09)

Operation result fingerprints are committed with the model window, avoiding repeated full chat/result snapshots while retaining authoritative evidence in PostgreSQL. Large results use bounded previews plus a task-scoped internal evidence read; this cannot dispatch external tools or verify an external action independently. At prompt budgets the saved model creates a compact working memo and the worker advances persisted budget baselines automatically. Lifetime accounting, a continuation cap and optional cost cap remain; exhausted hard caps pause with saved evidence. Migration 003 preserves legacy contexts and operation/approval identities. Existing chat UI and external RAG/ML services are unchanged.

## 2026-10-09 — ZSK manufacturing replacement

Reused the existing dedicated manufacturing PostgreSQL volume in the two-service `zsk-service/` stack; left core/chat/RAG schemas unchanged. Latest user instruction overrides the extended prompt’s persistent-label seeding: train from supplied labeled CSV, validate and activate immutable model, transactionally purge trained rows/drop old products/evaluation tables and seed unlabeled CSV. Startup remembers the phase and never reseeds labels. Missing initial joblib is built from supplied model code. Features are unchanged; chronological sorting and per-machine embargo added, with explicit metrics describing evaluation candidate vs final all-labeled fit. Keep bridge alias/host 8100 for generic registry compatibility; reset old tool permissions and enable only five read-only ZSK tools using a separate read token. Admin writes retain existing harness approval gates. No frontend or new agent.

ZSK discovery avoids regex schema constraints rejected by core: machine IDs still have bounded ASCII character validation in the service. MCP results use JSON-safe UUID/timestamp serialization. Live agent prediction and metrics calls succeeded after these compatibility fixes. No core permission rules were weakened.

## Manufacturing report evidence boundary (2026-10-09)

The report in `manufacturing-meta-harness/` uses the active ZSK service as its manufacturing case and treats the former manufacturing demo as historical. Source inspection, read-only deployment evidence, recorded historical tests and illustrative maintenance workflows are separated. The RAG asset ZSK-001 and measurement machine ZSK-SIM-01 are not joined by an inferred identity. The manual uses genuine existing captures with LaTeX viewport crops, preserving the original PNGs. Page budgets reserve two manual pages and keep the complete report within 30 pages. No application behavior is changed.

## 2026-10-09 — Autonomous simulation scope and durable interfaces

The user explicitly authorized the independent factory environment, Phaser rendering, forecast baseline, periodic ML, authenticated automatic tasks and simulation actions. Keep those domain mechanisms outside core and reuse the current ZSK database/model, generic MCP registry and persistent task engine. Do not revive the removed general event-trigger configuration.

- Fixed simulated five-minute sampling preserves existing rolling-feature cadence; monitoring defaults to ten simulated minutes. Monotonic clock origin avoids frame dependence/drift. Downtime freezes time; reset creates a new episode without deleting history.
- Factory JSON authority plus transactional measurement/action/event/outbox tables make recovery local and durable. Full versioned WebSocket snapshots favor simple resynchronization over delta bandwidth. Separate advisory-lock leaders prevent duplicate workers.
- Future-onset labels use separate generated episodes, chronological holdout, horizon/history embargo and causal observed features. The current classifier and purged historical training-label policy remain unchanged. No refit on holdout and no synthetic-to-industrial accuracy claim.
- Template-bound core event receipts atomically create existing tasks with explicit configured grants and immutable evidence checks. Service tokens cannot provide arbitrary requests, grants or commands. Stop-demo policy is explicitly enabled; restart and repair remain conservative.
- Machine-level active incident deduplication avoids parallel investigations when an evolving component hypothesis changes. Acknowledgment never implies recovery; fresh model evidence plus completed investigation resolves an incident, with cooldown.
- The real first demonstration exposed an LLM reusing an optional operation key across inspect and stop. Factory MCP now reads the Python SDK request context and prioritizes the persisted harness operation ID. Stable exact replay is safe; conflicting arguments still reject.
- Epoch-bound actions and inspection verification reject old tasks after simulation reset and unrelated inspection evidence. Separate browser/operator and MCP credentials prevent a task from inheriting operator privileges.
- The selected model repeatedly emitted multiple decision JSON objects and incomplete responses during the live test. The durable planner now uses exactly one forced native `submit_task_decision` function with the same strict schema and parallel calls disabled. Submission only proposes a decision; existing policy/ledger/approvals still control execution. It rejects multiple calls/text alternatives, validates arguments with the existing parser, records provider usage and appends a validation-only function acknowledgment to private model context. Incomplete output can expand the next bounded allowance to 32,768/context allowance while lifetime/prompt limits persist. Model failures remain visible and do not dispatch actions.

See `FACTORY_ARCHITECTURE.md` for domain contracts and `factory-service/README.md` for authorized configuration and actual verification evidence. Initial failed traces are preserved separately from successful fixtures/live runs.

The richer-report rerun exposed an additional context deficiency: the model could not distinguish granted writes from merely enabled backend policy because the grant list was absent from its snapshot. Context now includes the already-persisted server/tool grant scope on every update, without exposing private digests or adding authority. MCP text that is canonically identical to structured content is removed only from previews, preventing duplicate JSON from crowding evidence out of memory; originals and distinct text remain intact. Regression tests cover grant reconstruction and exact duplicate/distinct evidence behavior. The conservative partial-response trace is retained as `missing-scope-context-failure.json`.

## General-engineer manual and game walkthrough (2026-10-10)

The user requested a shorter, understandable narrative and more precise figures, then explicitly added the visualization game as the explanation vehicle. The main PDF was shortened to an 11-page guide following a simulated alarm through the line, sensors, separate models, persisted investigation, technician animation and operator repair/restart. Preserve the original 29-page technical audit with its date and source entry point. New editable diagrams distinguish material, power, thermal and software flows; plots use exact original CSV/saved operation values and identify timestamps, recipe boundaries, class orientation and evaluation limits. Copied game screenshots remain byte-identical and are cropped in LaTeX only. Source compilation is self-contained; data regeneration checks require the checkout. No domain/UI/core change is implied: known routing/deduplication, flash fallback and gearbox-only repair limitations are explained honestly. This is documentation work, with no new model evaluation or paid-provider run.

The follow-up request adds high-level agent assurances while keeping the complete manual below 20 pages. The guide is now 16 pages, expanding the backstage story into LLM connection, execution loop, tools/security, RAG, memory/context and validation/recovery. Two additional editable diagrams explain the loop and durable-record/working-context distinction. The narrative separates backend-enforced authority and completion predicates from model instructions, lossy memory and engineering judgment; planned external answer-validation workflows are not described as implemented. Numerical plots and saved evidence retain their original scope. Only documentation and delivery artifacts change.

The user's typography/placement correction selects genuine Calibri throughout the guide and black authored text, including diagram/chart labels, numbers and captions. Use LuaLaTeX/fontspec with four local Calibri faces from the mounted Windows installation; keep proprietary binaries in ignored build storage and out of source distribution. Preserve original screenshot pixels as evidence. Lighten formerly dark diagram boxes so black lettering stays readable. Attach the durable-notebook explanatory note with a dotted leader, position flow labels alongside their connections, and give vertical process boxes deliberate heading/body line breaks. Review every figure and complete page after the font change; data values and application behavior are unchanged.
