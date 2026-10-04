# MCP Integration Contracts

## General

The main application is an MCP client. It does not implement production MCP servers.

All runtime MCP tools must be explicitly allowlisted by the operator before a workflow may call them.

The core must discover tool names and input schemas from configured servers where the chosen MCP client library supports discovery.

## ML MCP

ML services are generic external model/enrichment services.

The main application makes no assumptions about their internal model type.

A workflow step binds to:

```text
server_id
tool_name
input_mappings
output_name
```

The tool result is preserved as the named step output and may be mapped into later ML steps or analyzer context.

No model-specific branching is allowed in core orchestration code.

## RAG MCP

A RAG profile binds to one external MCP server and one retrieval tool.

The RAG tool may expose any schema. The UI must allow explicit argument mappings for at least:

- operator prompt;
- selected workflow outputs;
- configured collection/index/profile;
- static values.

The core must preserve the external RAG result separately as retrieved evidence/context.

The core must not implement chunking, embedding, ranking, vector search, or reranking.

### Optional ingestion MCP tool

If the RAG server exposes an ingestion/registration tool, a RAG profile may bind it.

The operator explicitly invokes ingestion from the document UI.

The core forwards configured document metadata/reference to that tool and stores the returned status/result.

The core must not invent a file-transfer mechanism. If the external tool requires content or a URI, the UI/core must validate that the configured mapping can supply it; otherwise report a configuration error.

## Validator MCP

A validator profile binds to one external MCP tool.

The default execution point is after the analyzer produces a candidate answer.

The UI lets the operator map validator arguments from:

- candidate analyzer answer;
- operator prompt;
- ML step outputs;
- RAG evidence/result;
- full execution trace summary;
- static values.

The validator result is authoritative only as a validator output. The core must not silently merge or rewrite it into the model answer.

## Errors

For any MCP call, capture:

- connection error;
- timeout;
- tool-not-found;
- schema/argument error;
- server-returned error;
- malformed result.

Record the error in the step trace and surface a concise message in the UI.

Whether the run stops or continues after an ML-step error must be an explicit workflow behavior in the implementation. Codex may choose a simple v1 policy and document it in `docs/IMPLEMENTATION_DECISIONS.md`; do not hide failures.
