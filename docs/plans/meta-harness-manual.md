# Goal
Produce an A4 LaTeX technical manual, 20-30 pages, grounded in the current source and real UI.

## Motivation
Explain how the selected LLM, execution loop, durable memory, MCP, policy and verification form this specific application.

## Existing architecture
React/Vite/shadcn UI, NestJS core, PostgreSQL chat/tasks, independent FastAPI RAG and manufacturing services.

## Proposed design
Approximately 27 pages: title/contents, 14 numbered chapters, source pointers, diagrams, genuine screenshots, references. Active capabilities, removed triggers and unavailable retraining are explicitly separated. All authoring stays under docs/meta-harness-manual; no application behavior changes.

## Implementation steps
Audit code and verification records; consult the requested paper; capture UI; author chapters/TikZ figures/BibTeX; compile with a temporary LaTeX toolchain; render and inspect every page; fix layout and update the project map.

## Validation
Compare major mechanisms with functions/schema. Read-only runtime checks and screenshot capture. Compile passes, zero unresolved references, maximum 30 pages, visual review of all rendered pages and sensitive-data inspection. Historical test records are attributed, not reported as rerun.

## Evaluation impact
None.

## Risks
Some canonical prose is stale: current manufacturing production labels are removed and retraining is unavailable. Screenshots may include historical fixture evidence; label captures accurately. No keys or secret values enter the manual. Compiler/browser dependencies remain temporary.
