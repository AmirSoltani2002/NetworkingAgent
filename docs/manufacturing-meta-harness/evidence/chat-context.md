# Chat context verification — 2026-10-09

| Executed check | Result |
| --- | --- |
| Full npm test (local fixture sockets permitted) | UI: 19 passed; core: 24 passed, 3 optional PostgreSQL tests skipped |
| Isolated PostgreSQL tests in the rebuilt core image | All 3 passed; temporary `_tests` database removed afterward |
| Final chat UI regression run after confirmation cleanup | All 5 passed, including automatic continuation and consumed-confirmation retry |
| npm run build / typecheck / lint; git diff --check | Passed; final UI build/lint/whitespace checks also passed |
| Docker core/UI image builds and recreation | Passed; existing MCP bridge preserved |
| Running database upgrade and core health | context_window column present; /api/health returned HTTP 200 |
| Rendered Docker UI with browser-only fixtures | Three budget checkpoints, four response prompts, one user message and one final reply; no duplicate bubbles |

Core fixtures exercise the exact 90% boundary, below-threshold behavior, complete compact-window carryover, model changes, invalid/ineffective compaction, eight-turn and twelve-call checkpoints, deadline renewal and no MCP replay. Existing authorization/decline/schema-change/interrupted-execution tests passed. PostgreSQL checks include idempotent upgrades, private context persistence across service recreation, message watermark correctness, original transcript preservation and public-response secrecy.

The initial sandboxed full-suite invocation could not run local HTTP/MCP fixtures; the permitted rerun passed. Final browser screenshots were inspected against the approved black layout: [responding](../screenshots/ui-context-responding.png), [completed](../screenshots/ui-context-completed.png). Tests use mocked provider responses/token counts/compaction and an aborted deadline signal; they do not execute a paid live compaction or wait two real minutes. No manufacturing/RAG internals were changed or retested.
