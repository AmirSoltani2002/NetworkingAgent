# Acceptance Tests

The implementation must include automated tests covering these behaviors. Exact test file names are an implementation decision.

## MCP registry

- Add/edit/delete an MCP server.
- Connection test failure is shown without crashing core.
- Tool discovery stores descriptors.
- A non-allowlisted tool cannot be used by a workflow.
- No raw secret is returned to the browser.

## Workflow builder

- Create a workflow with at least three ML MCP steps.
- Reorder steps and persist the new order.
- Disabled steps are skipped.
- Input mapping from operator prompt works.
- Input mapping from prior step output works.
- Missing referenced prior output is rejected before run.
- Workflow version used by a completed run remains immutable in run history.

## RAG/documents

- Create a RAG profile bound to an external MCP server/tool.
- Register a document and map it to a RAG profile/collection.
- Document ingestion is unavailable when no ingest tool is configured.
- When an ingest tool is configured, the core invokes the external MCP tool rather than performing ingestion itself.
- Retrieved RAG output is stored/displayed separately as evidence/context.

## Validator

- Configure a validator profile.
- Validator runs after analyzer candidate answer.
- Validator receives explicitly mapped inputs.
- Validator failure/result is displayed separately from the analyzer answer.
- Validator output does not silently rewrite the analyzer answer.

## Operator console

End-to-end test with mock MCP fixtures:

1. register mock ML MCP A;
2. register mock ML MCP B;
3. register mock RAG MCP;
4. register mock Validator MCP;
5. create workflow A -> B;
6. map B input from A output;
7. configure RAG profile;
8. configure analyzer profile;
9. configure validator profile;
10. submit operator prompt;
11. assert call order A then B;
12. assert analyzer receives prompt + selected ML outputs + RAG context;
13. assert validator receives candidate answer and configured evidence/context;
14. assert final UI/run record exposes all step traces and timings.

## Local deployment

- One documented local startup command starts `ui` and `core`.
- No AWS credentials/services are required.
- No Terraform is present.
- No production ML/RAG/validator implementation exists in the main application.

## Quality

The repository must provide and pass lint/type/test commands appropriate to the chosen stacks.
