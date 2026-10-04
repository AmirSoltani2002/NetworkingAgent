# Codex Implementation Task

Implement the LOCAL main meta-harness application described by this repository.

Read `AGENTS.md` first and then all referenced specification files.

## What you are implementing

Implement only:

1. the browser UI/control plane;
2. the minimal local `core` backend/orchestrator needed by the UI;
3. generic MCP client integration;
4. local persistence of configuration and run traces;
5. local container/development setup for `ui` and `core`;
6. tests and mock MCP fixtures needed to prove the UI flow.

## What you are NOT implementing

Do not implement:

- AWS or any cloud infrastructure;
- real ML models;
- model training;
- a vector database or RAG engine;
- domain-specific retrieval logic;
- validator algorithms/functions;
- BGP data providers;
- external MCP servers as production services.

Mock MCP servers are allowed only under test/dev fixtures to exercise the main application.

## Required operator flow

The final application must let the user perform this sequence entirely from the UI:

1. Add an MCP server representing an ML service.
2. Connect/introspect it and choose one exposed tool.
3. Add more ML MCP/tool steps if desired.
4. Reorder ML steps with an explicit ordered workflow editor.
5. Configure input mappings for each step.
6. Add/register documents.
7. Assign each document to a configured RAG MCP plus collection/index/profile identifier.
8. Configure the RAG retrieval MCP tool.
9. Configure the validator MCP and validation tool.
10. Configure the analyzer/LLM profile.
11. Open the Operator Console.
12. Enter a question/prompt.
13. Run the workflow.
14. Observe progress by step.
15. Inspect ML outputs, RAG evidence, analyzer answer, validator result, errors, and timing.
16. Re-open the completed run from run history.

## Implementation authority

You own lower-level software design. Make routine technical decisions yourself and document non-trivial choices in `docs/IMPLEMENTATION_DECISIONS.md`.

Do not broaden the project scope or implement external domain services.

## Final report

When finished, report:

- files created;
- files modified;
- architecture/design choices made;
- commands run;
- test/lint/type-check results;
- any blocked high-level decision.
