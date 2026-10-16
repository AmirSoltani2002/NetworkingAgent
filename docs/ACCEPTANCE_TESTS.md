# Acceptance Checks and Validation Status

This document covers the current chat foundation. Future workflow acceptance is owned by [ROADMAP.md](ROADMAP.md).

## Current acceptance checklist

| Area | Required behavior | Recorded result on 2026-10-08 |
| --- | --- | --- |
| Local startup | All three images build; Compose services become healthy | Passed |
| Frontend/backend | Production builds and ESLint complete | Passed |
| Visual review | Desktop/mobile captures preserve the approved chat layout | Captured and inspected |
| Chats | Generated titles, selectable saved history, and New chat work | Reviewed in browser |
| Text and files | Text/file sends save; file downloads return original bytes | Reviewed |
| Persistence | History and attachments survive browser reload and all-service restart | Reviewed |
| Retry | Same message UUID does not create a duplicate | Reviewed |
| Invalid input | Empty submission and invalid UUID return 400 | Reviewed |
| Cleanup | Only review-created sample chats are removed | Completed |

These results refer to the original chat implementation review, not to checks rerun for later configuration/documentation changes. Representative captures are linked in [UI_SPEC.md](UI_SPEC.md).

## Available code checks

The root package.json defines:

- npm run build: builds both workspaces; frontend build also checks TypeScript.
- npm run typecheck: checks TypeScript in both workspaces.
- npm run lint: checks frontend/backend source and selected tooling files with ESLint.

UI chat/RAG and core registry/provider/SDK/credential/PostgreSQL regression suites are available. Latest results are recorded below; standalone RAG has its own suite. Manual browser/API review and build/lint results must not be described as automated test coverage.

## Remaining coverage

When automated coverage is requested, include message limits, multipart edge cases, title boundaries, file-only messages, transaction rollback, filename handling, download/chat ownership, concurrent saves, retry conflicts, browser load cancellation, and failure-draft preservation.

MCP SDK/provider fixtures are implemented; ordered workflow/validator tests remain future work. Keep external service logic outside core and use separate disposable service fixtures for integration tests. The separately requested RAG service has its own suite.

## UI review procedure

For UI changes, capture the rendered app at the user's reference size and mobile widths, inspect it against the supplied picture and approved interactions, adjust the implementation, and repeat. The final reviewed state must match the requested UI scope. Startup and environment instructions are in [OPERATIONS.md](OPERATIONS.md).

## Environment-secret configuration

The root .env is ignored by Git and Docker build contexts. Compose requires DB_PASSWORD for core/database; native core loads .env before module creation and rejects missing/blank credentials. .env.example keeps confidential values empty; non-secret defaults are documented. General settings remain documented in OPERATIONS.md.

This configuration change does not add an automated test suite. Future requested coverage should include root/workspace startup paths, missing/blank secret rejection, generic file-read errors, injected-environment precedence, and exclusion of secrets from frontend/API/log/trace output.

For this configuration update, native/backend-image builds completed and Compose reported all three services healthy. Documentation links and diff whitespace were checked. Secret values were not printed. No application tests were added or run.

## Collapsible Chats review

The frontend image built successfully and the updated Compose UI became healthy. Desktop/mobile expanded and collapsed screenshots were captured and visually inspected against the supplied reference within the approved scope. Browser review confirmed title hiding, visible heading/chevron state, unchanged active conversation/draft, Space-key reopening, and no mobile horizontal overflow or runtime exceptions. Only the temporary review chat was removed; existing chats were preserved. No automated test suite was added.

## OpenAI configuration review — 2026-10-09

Native production builds and lint passed. Docker Hub base-image resolution timed out twice; the already compiled output was packaged using the existing cached Node/Nginx runtime images. The updated Compose services are healthy; core's narrow .env mount is writable without changing file contents during that access check.

At that configuration review, the live settings route returned only public fields with no-store headers and no OPENAI_API_KEY was configured. The live model-list route correctly requested a saved key; real account model discovery was not reviewed then. The user subsequently saved a key/model before the inference step below.


An isolated native instance of the compiled LlmModule, private temporary .env, and fixture OpenAI catalog demonstrated key entry/clearing, four-character-plus-stars responses, actual temporary-file persistence, model/thinking saves, and LLM collapse/expand. Desktop/mobile captures were inspected; no runtime exceptions or horizontal overflow were observed. User .env/database contents were not changed by this review. No automated test suite or paid inference was used.

## Chat inference review — 2026-10-09

Production build, typecheck, and lint passed. Fresh compiled assets/schema were packaged using the existing cached local runtime images (same dependencies/base versions), and all three Compose services became healthy. Source Dockerfiles retain the normal multistage recipes. The existing database volume was upgraded with reply linkage without deleting user data.

Manual browser/API review used the saved gpt-6-luna model and Instant thinking for three short real replies. The first greeted Ada; the follow-up remembered Ada from history. A repeated response request returned the same saved assistant UUID. Reload reopened persisted user/assistant messages. A browser-intercepted 503 simulated a response connection failure: the user remained saved, the composer was cleared, an error/retry appeared, and reopening preserved the unanswered state. Explicit retry then received a real third answer. No user key/model/thinking was changed.

Desktop (1808×882) and mobile (390×844) captures were inspected against the supplied reference. The initial capture exposed inherited blue styling on assistant paragraphs; styles were scoped to users, redeployed, recaptured, and inspected. Final assistant answers are white and left aligned. Mobile width stayed 390px; no browser runtime exceptions were observed. Temporary review data was removed while retaining existing chats.

No automated test suite was added or run. Medium/High, incompatible model/effort, quota, provider timeout/incomplete/malformed output, concurrency under a live provider request, and crash/billing ambiguity were not exercised. Future requested coverage should include those cases, cross-chat input isolation, unique reply linkage, migration repetition, foreign-origin rejection, context limits, and retry after uncertain completion.

## 2026-10-09 — Standalone RAG and MCP registration validation

- **30 pytest tests passed** in the committed multi-stage Docker test target against isolated PostgreSQL 17/pgvector. Coverage includes six-table migrations/downgrade/repeat/model mismatch, device/issue CRUD and embeddings, uploads/duplicate files/applicability/deletion, PDF/TXT/Markdown extraction, actual LlamaIndex semantic splitting, protected procedures and page provenance, vector/FTS/RRF scopes, direct retrieval without issues, shared manuals, explicit evidence, failed ingestion/retries/reprocessing/interrupted final attempt, MCP HTTP tools/auth, sanitized logging and declared/streamed body limits. Real pinned local embeddings **and cross-encoder** were exercised. No generative LLM/API dependency was used.
- **2 core MCP tests passed**, using an official SDK fixture for URL/credential validation, discovery, read-only allowlisting, redaction/missing/bad credentials and proof that discovery never executes tools. `npm run build`, `npm run typecheck`, `npm run lint`, Python Ruff and diff whitespace checks passed.
- Production RAG image built and its database/API/worker became healthy. Live REST/MCP review uploaded and automatically ingested Device A/B/shared manuals using actual local embeddings, checked device scopes, manual-only retrieval, correct sources, explicit evidence and atomic reprocessing. Temporary review records/files were deleted.
- Existing app images rebuilt normally from committed Dockerfiles; database/core/UI became healthy with existing chats preserved. Browser UI added **Local RAG**, discovered four tools and explicitly saved their read-only allowlist. Registration persists; credentials remain root `.env` references. Desktop/mobile final captures were inspected against the user's reference, including compact form/tool views and no horizontal overflow.
- Documentation links were checked. Secrets were not printed or embedded in images/frontend assets. No workflow, chat RAG execution, analyzer, validator or execution-trace acceptance is claimed. GPU deployment, OCR and distributed load/failure testing remain outside the performed checks. Upstream test/model-download deprecation warnings remain non-fatal.

Reproduce core checks with `npm run test --workspace core`; reproduce retrieval checks using `rag-server/docker-compose.test.yml` as documented in its README. Never run destructive RAG tests against a knowledge database.

## 2026-10-09 — Existing-app RAG integration

- **11 UI tests passed** (Vitest/Testing Library/jsdom): independent collapsible navigation, connection/draft permission guard, separate health/errors, write-only token clearing, save/permissions, device CRUD/counts/confirmed deletion, issue editing, explicit passage evidence linking, multipart upload/associations, retrieval sources/empty/timeouts, polling to ready, preserved draft and ordinary chat save/reply regression.
- **11 core tests passed**, including real disposable PostgreSQL: idempotent schema upgrades/registry update parameter types, chat title/history/file bytes/source metadata/reply idempotency; serialized private .env writes/conflicts; URL/origin/IP/REST-path security; actual official SDK discovery/execution/revocation/read-only enforcement/secret-safe failures; REST auth/multipart/204/redirect errors; independent MCP/REST health and unsaved authentication isolation; Responses model-selected function loop/encrypted reasoning continuation/source traces/no forced tool calls; unregistered function refusal and provider authentication failure; logging/parser-error secret exclusion. The optional test DB was supplied through CORE_TEST_DATABASE_URL with a _test suffix.
- Native build/typecheck/lint and multistage Docker ui/core/database image builds passed. The existing application containers were recreated with their original persistent volume/settings and became healthy. External RAG image/implementation/database/models were not rebuilt or modified. Its prior pytest results above were not rerun for this integration.
- Live browser scenario against the actual external server: save/test independent endpoints, discover/enable four read-only tools, create/edit Device A, upload/process an actual PDF, create/update an issue, search/select/link diagnostic evidence, remove/relink evidence, inspect chunks/sources and device-scoped retrieval. A shared manual was searchable for Device B with no known issues. A corrupt PDF failed in the external worker and accepted a retry. REST deletion cleanup succeeded.
- One live response used the unchanged saved gpt-6-luna/Instant settings: the existing model selected find_device, search_knowledge and get_document_context; all succeeded, source references persisted, and its chat answer distinguished possible cause from confirmation. No new agent/model or forced-call application rule was added. A final direct permitted MCP call from the deployed core image after restart verified retained connection/permission settings and fresh retrieval sessions without another provider request.
- Desktop captures at 1808×882 and mobile at 390×844 were inspected against the approved black layout. Compact RAG navigation/main-area forms, plain white assistant text, blue user bubble, original 768px chat/composer and Send/file controls remain. Final mobile captures had no horizontal overflow; browser checks reported zero runtime exceptions. Old MCP form/types/captures and completed plan were removed.
- Only explicitly identified review knowledge/chat and the disposable PostgreSQL/browser fixtures were removed. Existing chats, saved LLM configuration and secrets were retained. Local RAG remains saved, connected and retrieval-enabled.

## 2026-10-09 — Manufacturing ML/MCP demonstration

- The isolated Docker test stack passed **12 pytest tests** against disposable PostgreSQL after the final service schema-validation changes. The suite covers deterministic seed/constraints, frozen holdout exclusion, training/inference/artifact persistence/retraining, nonblocking failure behavior, bounded dataset classification and live HTTP/MCP authentication/tool contracts. One Starlette/httpx deprecation warning remains.
- Fresh root `npm test`: **17 UI tests passed; 16 core tests passed; two optional PostgreSQL tests skipped** because CORE_TEST_DATABASE_URL was not set for that invocation. A separate earlier run with isolated PostgreSQL completed all **18 core tests**. Production build and lint commands completed successfully during the implementation.
- The local demo database contained 1,000 seeded synthetic products. A live actual-model prediction, full bounded dataset classification, and metrics retrieval worked through the existing gpt-6-luna/Instant chat and deployed MCP connection. See [prediction](verification/manufacturing-agent-prediction.json), [dataset](verification/manufacturing-agent-dataset.json), and [metrics](verification/manufacturing-agent-metrics.json).
- Live training required the exact confirmation, survived browser reload, and produced one job with status `ready`. The agent called `train_quality_model` and `get_training_status`; the latter returned the actual held-out evaluation metrics, so the separate metrics tool was not needed. Model version `v-dd596523-1001-4e41-aba3-f03da33815a7`, 800 training rows, 200 held-out rows, 67% accuracy, 51.5% majority baseline. Ground-truth labels were unchanged. The initial browser-check script incorrectly required a redundant separate metrics-tool call; its assertion was corrected here based on the persisted successful trace. See [training trace](verification/manufacturing-agent-training.json) and [confirmation screenshot](screenshots/ui-mcp-training-confirmation.png).
- An ordinary chat, desktop/mobile visual comparison for the new MCP navigation, live reconnection after a Meta-Harness process restart, and adversarial network/schema stress were not rerun in this final pass. No production-data accuracy claim is made for this synthetic sample. The independently documented RAG tests were not rerun for this demo.

Remaining coverage includes provider billing/crash ambiguity, live Medium/High and quota/long-duration cases, all upload/multipart boundary variants, large-catalog load tests, malicious schema fuzzing and DNS-rebinding adversarial fixtures. No ordered ML/validator workflow acceptance is claimed.

## 2026-10-09 — Chat context and automatic continuation

Provider fixtures passed for the 90% token boundary, same-model compaction, complete window carryover, model changes, failed compaction and prompt checkpoints. The full suite passed with 19 UI/24 core tests and 3 optional DB skips; all 3 DB tests then passed against an isolated temporary PostgreSQL database using the rebuilt core image. After the final consumed-confirmation cleanup, all 5 chat UI tests passed. Build, typecheck, lint and whitespace checks passed. Core/UI images were rebuilt and deployed, the context column was verified on the existing volume, and core health returned 200. Rendered browser fixtures demonstrated three automatic checkpoints with one final reply; final screenshots were inspected. Exact evidence and limits are in [chat-context verification](verification/chat-context.md). No paid live provider compaction or real two-minute wait was executed.

## Persistent tasks — executed 2026-10-09

- Final complete backend suite against durable_tasks_tests: **35 passed, 0 failed, 0 skipped** (includes chat PostgreSQL regressions and durable engine). UI suite: **24 passed**. Full backend output is saved in [task-backend-tests.log](verification/task-backend-tests.log).
- Typecheck, lint, production UI/core builds and Docker image builds passed. BuildKit registry metadata lookup timed out; the same Dockerfiles built successfully with the local legacy builder and host networking.
- Actual SIGKILL/restart of a running core-image fixture after a completed MCP write: resumed task COMPLETED, database write count 1, write attempts 1, interrupted read attempts 2. Uses actual PostgreSQL/official MCP/worker with deterministic planner; see [restart results](verification/task-restart.json).
- Initial combined database regression failed because the crash-fixture worker was still polling the same test database. Stopped that fixture and reran all four database cases successfully; test workers must use isolated databases or stop competing fixture workers.
- Deployed UI-proxied health/task/policy routes, invalid-request rejection, webhook authentication, schedule create/update/history/delete and SSE headers passed; [HTTP results](verification/task-http.json). Temporary schedule removed.
- Rendered desktop 1808×882 and mobile 390×844 screenshots inspected against the approved dark sidebar/main-area style. Corrected initial table spacing and mobile wrapping, rebuilt, captured and inspected final screens: [active tasks](screenshots/ui-tasks-active.png), [details](screenshots/ui-tasks-details.png), [schedule](screenshots/ui-tasks-schedule.png), [mobile](screenshots/ui-tasks-mobile.png). Browser-only task records demonstrate rendering; no model calls or persistent chat fixtures were created by visual review.
- Both ordered migrations are recorded in the existing application database. Core/database/ui containers healthy after recreation. No paid live OpenAI autonomous task was executed; structured decision/provider tests use fixtures.

Policy limits and remaining supported execution boundaries are documented in [TASK_EXECUTION.md](TASK_EXECUTION.md#limits).

## Task chat feedback and trigger removal (2026-10-09)

Task outcomes and request/output history now appear in chat with opt-in task details navigation. Event-trigger configuration, intake and execution are removed temporarily; schedules remain. Build/typecheck/lint were run for this change. Browser screenshot review could not run because computer-use inventory returned no browsers or apps; previous screenshots do not verify this change. No new paid-model task or container-restart scenario was executed for this change.

Automatic scope/direct response change: build/typecheck/lint validation only. No paid-model task or restart/replay scenario was executed for this increment; text delivery is explicitly distinguished from external verification.

## Task formatting recovery (2026-10-09)

Build and lint passed. The actual failed user ML analysis task was resumed after deployment: get_manufacturing_dataset, classify_manufacturing_dataset and get_quality_model_metrics each succeeded with one attempt. Plain argument-filter normalization allowed all three immutable checks to pass. The saved completion response was recovered without replaying any tool; task state is COMPLETED, progress 100, last_error null, and the response is saved in the conversation. This is executed user-task evidence, not a general regression-suite result.

## Read-only RAG recovery (2026-10-09)

Build and lint passed. The actual CNC task had passed a device name as device_id and received INVALID_SEARCH. After deployment and retry, the rejected invocation was not replayed: find_device, corrected search_knowledge and get_device_issues each succeeded once; three of four checks passed. The remaining source-context check was not completed: accumulated usage reached 286,774 tokens over seven model turns against the configured 200,000-token budget. The task retained FAILED status and saved successful evidence; full task completion is not claimed. The retry route was also corrected for PostgreSQL parameter-type inference (status update now casts its text parameter explicitly).

## Task context checkpoints — 2026-10-09

Core TypeScript/Nest build, all-workspace typecheck and repository lint passed. The core image built and was deployed; migration 003 was applied and GET /api/health returned 200. The actual authorized CNC retrieval task was retried from its saved checkpoint, summarized by the saved model and completed with all four existing verification predicates true. The previously successful device lookup, search and issue calls each retained one attempt. Only the missing get_document_context call was added, followed by a saved response. The first new snapshot seeded conversation/tools; the next omitted both and delivered only the new operation result. Private delivery state is excluded from the task API. [Recorded results](verification/task-context-checkpoints.json) include actual token baselines and scope limitations. No new automated suite, crash/concurrency, fresh-budget-boundary or evidence-paging run was executed in this change. The frontend was unchanged.

## 2026-10-09 — ZSK replacement

Actual labeled training → purge → unlabeled inference completed; final dataset has 0 labeled/1000 unlabeled rows and 1000 separate model predictions. Isolated model/DB checks, live official MCP/auth/idempotency and real saved-agent prediction/metrics calls passed. Current details, encountered/fixed integration issues and scope limitations are in [zsk-results.md](verification/zsk-results.md). Core/UI/RAG full suites were not rerun.

## Factory simulation verification — 2026-10-09

Recorded evidence lives in `docs/verification/factory/`. Twelve isolated Python tests passed on `factory_tests`: deterministic clock/speeds/pause, all eight correlated scenarios, causal forward labels/chronological embargo, state/technician/maintenance permissions, no inference labels, real PostgreSQL persistence, operation replay/recovery, monitoring outage/cursor retention, alarm/outbox deduplication, authenticated strict MCP (17 tools), harness-key precedence, epoch guard and WebSocket resync. One upstream Starlette test-client deprecation warning remains.

The real container recovery test (`recovery-check.json`) passed with `factory_recovery_tests`: browser-independent measurements, factory/PostgreSQL restart, stable episode/clock/completed inspection, idempotent replay, ML stop/start with retained cursor, durable pending alarm while core unavailable, and no duplicate incident. Five actual PostgreSQL core tests passed (registry/chat/context, durable engine approvals/leases/retries/recovery/schedules, authenticated atomic integration receipts). An obsolete test assertion for the removed generic event-trigger API was replaced with rejection coverage; that feature remains removed.

`task-restart.json` records an actual isolated task-container SIGKILL during read verification after a completed MCP write. Automatic recovery reached COMPLETED; write count/attempts stayed one, read attempts became two, deterministic verification passed. The original fixture container was left untouched; the factory-specific fixture uses its own name/loopback port.

`browser-check.json` passed with six real screenshots at 1600×1000 and 1280×900: rendered Phaser, live WebSocket, component click, monitoring/settings/alarms navigation and preserved unsent chat draft; no console exceptions. Screenshots were visually inspected against both supplied references. Sensor chart values come from actual stored records.

The first real-provider attempts failed safely (operation-key conflict and incomplete/conflicting text decisions); traces are retained and fixes documented. The fresh unattended run `end-to-end.json` passed: automatic sensor-derived task, real current/forecast metrics, scoped RAG issues/passages, actual completed gearbox inspection, permitted simulated stop, exact machine/episode verification, alarm acknowledgment, all six immutable checks and operator report. Task `9be6ccdb-b5e1-48cb-8966-ea32f757935c` completed in 15 turns, 68.2 seconds active execution. This is a software integration demonstration on synthetic data, not industrial validation. Final delivery verification counts are additionally recorded in `checks.json`.

Final deployed run: task `306f5c12-5c55-486c-9d5b-5670fb5cf506`, COMPLETED, 14 turns, 112.7 seconds active execution; no operator intervention after scenario setup. All six immutable checks plus explicit inspect/stop/ack action checks passed; inspection ID matched the actual backend record. The report includes actual alert/pre-stop/post-stop sensor values, separate model metrics, specific RAG document/chunk references, verified actions, recommendation and uncertainty. A temporary model-decision retry was recovered automatically. `operator-report.md` preserves the actual model output. The final model-context fixes expose existing grant scope and omit only exact duplicate JSON previews; bounded machine-state responses and small history queries keep sensor values visible. Final regular suites: 25 UI and 37 core passed (five optional database tests run separately: five passed); 12 factory tests and 18 existing ZSK lifecycle checks passed. Build/typecheck/lint, browser, real container recovery and task SIGKILL recovery passed. Plot-label inherited icon strokes and initial technician position on browser refresh were corrected during visual QA.
