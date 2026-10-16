# Simulation change manifest

This is the task-specific change set, not a report of all pre-existing dirty files in this checkout.

## Created

- Independent service: `factory-service/factory/{__init__,config,cli,domain,store,worker,api,mcp_server}.py`.
- Schema: `factory-service/migrations/001_factory.sql`, `zsk-service/migrations/004_forecast.sql`, `database/migrations/004_task_integrations.sql`.
- Deployment/guide: `factory-service/{Dockerfile,docker-compose.yml,docker-compose.test.yml,docker-compose.recovery-tests.yml,.env.example,README.md}`, root `docker-compose.factory.yml`.
- Setup/demo/tests: `factory-service/scripts/{configure,demo,recovery_check,browser_check}.py`, `factory-service/tests/{test_domain,test_database,test_api}.py`.
- Forecast/scenarios: `zsk-service/zsk/{synthetic,forecast}.py`.
- Core: `core/src/integrations/{integration-contract,integrations.controller,integrations.module}.ts`, `core/src/factory/{factory.controller,factory.service,factory.module}.ts`, `core/config/task-integrations.json`, `core/tests/{integrations,integration-database}.test.cjs`.
- UI: `ui/src/components/factory/{factory-navigation,factory-workspace,factory-canvas}.tsx`, `factory-scene.ts`, `factory.css`; `ui/src/lib/factory-api.ts`, `ui/src/types/factory.ts`, `ui/tests/factory.test.tsx`.
- Engineering/evidence: `docs/FACTORY_ARCHITECTURE.md`, `docs/verification/factory/` metrics, execution traces, screenshots, test logs and this manifest.

## Modified

- `zsk-service/zsk/{config,api,mcp_server}.py`, `zsk-service/{Dockerfile,docker-compose.yml,README.md}`: separate forecasting endpoints/model/registration while preserving existing current classifier.
- `core/src/app.module.ts`, `core/Dockerfile`, `core/package.json`: integration/gateway modules, config packaging, WebSocket dependency.
- `core/src/llm/llm.service.ts`, `core/src/tasks/{task-prompt,task-context}.ts`: strict one native next-decision submission, bounded incomplete retry and persisted context/usage.
- `core/tests/{tasks-llm,tasks-database,tasks}.test.cjs`, `core/tests/{task-restart-fixture.cjs,task-restart-review.py}`: native decision regression, removed-trigger rejection, isolated configurable SIGKILL fixture.
- `database/schema.sql`: receipt snapshot.
- `ui/src/{App.tsx,components/chat/sidebar.tsx}`, `ui/{package.json,vite.config.ts,nginx.conf}`, `ui/tests/chat.test.tsx`: factory navigation preserving chat, lazy Phaser, WebSocket proxy, existing prefixed-error test matcher.
- Root `package-lock.json`, `.env.example`, `README.md`, `AGENTS.md`; owning documents `docs/{LOCAL_ARCHITECTURE,UI_SPEC,DATA_MODELS,API_SPEC,MCP_CONTRACTS,TASK_EXECUTION,OPERATIONS,PROJECT_MAP,IMPLEMENTATION_DECISIONS,ACCEPTANCE_TESTS}.md`.
- Ignored root `.env` only: generated scoped secrets, approved origins/profile IDs, explicit RAG mapping and requested stop-demo policy. No secret values are included in this manifest or committed examples.

## Runtime result

Factory is an added independent API/MCP/background worker on loopback 8110. Existing ZSK image adds forecasting; core/UI gain generic event receipt/gateway and the factory workspace. No new PostgreSQL container is added to runtime; factory shares the current private manufacturing database. RAG is unchanged. UI remains loopback 8080.

Automatic stop is explicitly enabled for the requested simulation demonstration; automatic restart/maintenance are false. Defaults in source/examples are all false. Seventeen Factory MCP tools and two read-only forecasting tools are registered/allowlisted through the generic interface. Database migrations are additive; historical labels remain purged. Actual checks/results are in `checks.json`, `end-to-end.json`, `recovery-check.json`, `task-restart.json` and `browser-check.json`.
