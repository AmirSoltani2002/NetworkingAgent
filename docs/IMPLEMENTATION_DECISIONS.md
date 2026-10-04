# Implementation Decisions

Codex owns lower-level software design and must record non-trivial choices here instead of asking the user about routine engineering details.

For each decision record:

## YYYY-MM-DD — Decision title

**Decision:**

**Reason:**

**Alternatives considered:**

**Affected modules/files:**

Do not use this file to change the fixed product boundary in `AGENTS.md`.

## 2026-10-04 — Dependency-light local stack

**Decision:** Implement the core as a Python standard-library HTTP service with SQLite persistence, and the UI as a vanilla JavaScript single-page application served by Nginx. Use Docker Compose for the local UI/core startup path.

**Reason:** The initial repository contained only specifications. This keeps the first local version easy to run, inspect, and test without cloud services or a frontend build system.

**Alternatives considered:** FastAPI plus a framework-based frontend; a single-process UI/API server.

**Affected modules/files:** `core/server.py`, `core/Dockerfile`, `ui/`, `docker-compose.yml`.

## 2026-10-04 — Generic MCP and analyzer adapters

**Decision:** Speak MCP JSON-RPC over streamable HTTP with initialize/session support, discover tools from `tools/list`, and call only explicitly allowlisted descriptors. Implement the initial analyzer adapter against OpenAI-compatible Chat Completions. API tokens are resolved from core environment variables by reference name.

**Reason:** This keeps domain capabilities replaceable and makes the configured tool/schema metadata the only execution binding.

**Alternatives considered:** Provider-specific SDK clients; a separate MCP client dependency.

**Affected modules/files:** `core/server.py`, `ui/app.js`, `README.md`.

## 2026-10-04 — Immutable run configuration snapshot

**Decision:** Capture the workflow, analyzer, and selected validator profiles in each run record before dispatching its background execution. Persist sanitized tool arguments in traces.

**Reason:** A later edit to a profile must not change the configuration associated with an already submitted run; trace records also should not retain credential-like argument values.

**Alternatives considered:** Store only profile IDs and retrieve the latest profile during execution; rely on trace output alone to reconstruct run configuration.

**Affected modules/files:** `core/server.py`, `tests/test_core.py`.

## 2026-10-04 — Workflow error policy

**Decision:** A failed ML or RAG call ends that run and records the error. A validator call occurs after the analyzer; validator errors are recorded separately while preserving the analyzer answer. Cancellation is reported as unsupported in v1.

**Reason:** This makes failed dependencies explicit while retaining the candidate answer when only the post-analysis validator is unavailable.

**Alternatives considered:** Continue after failed ML steps; fail the whole run on validator error; implement cooperative cancellation.

**Affected modules/files:** `core/server.py`, `ui/app.js`, `README.md`.
