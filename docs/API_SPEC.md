# Local Core API Specification

The UI talks only to the local core API. Exact route organization below is required behavior; serialization details may be refined by Codex while keeping compatibility with the UI.

## MCP registry

```text
GET    /api/mcp/servers
POST   /api/mcp/servers
GET    /api/mcp/servers/{id}
PATCH  /api/mcp/servers/{id}
DELETE /api/mcp/servers/{id}
POST   /api/mcp/servers/{id}/test
POST   /api/mcp/servers/{id}/discover
PATCH  /api/mcp/servers/{id}/tools/{tool_name}
```

`discover` refreshes tool descriptors from that MCP server.

The tool patch supports explicit allowlist enable/disable.

## Workflows

```text
GET    /api/workflows
POST   /api/workflows
GET    /api/workflows/{id}
PUT    /api/workflows/{id}
POST   /api/workflows/{id}/duplicate
POST   /api/workflows/{id}/validate
```

Saving an existing workflow creates/advances a version; completed run records continue to reference the version used at execution time.

## RAG/documents

```text
GET    /api/rag/profiles
POST   /api/rag/profiles
PUT    /api/rag/profiles/{id}
DELETE /api/rag/profiles/{id}

GET    /api/documents
POST   /api/documents
GET    /api/documents/{id}
PUT    /api/documents/{id}
DELETE /api/documents/{id}
POST   /api/documents/{id}/ingest
```

`/ingest` is valid only when the assigned RAG profile has an external ingestion tool configured. The core calls that MCP tool; it does not perform RAG ingestion itself.

## Analyzer profiles

```text
GET    /api/analyzers
POST   /api/analyzers
PUT    /api/analyzers/{id}
DELETE /api/analyzers/{id}
```

## Validator profiles

```text
GET    /api/validators
POST   /api/validators
PUT    /api/validators/{id}
DELETE /api/validators/{id}
```

## Runs

```text
GET    /api/runs
POST   /api/runs
GET    /api/runs/{id}
GET    /api/runs/{id}/trace
POST   /api/runs/{id}/cancel
```

`POST /api/runs` accepts:

```text
workflow_id
analyzer_profile_id
validator_profile_id | null
operator_prompt
```

The response returns a run ID immediately. The UI then observes the run/trace through polling, server-sent events, WebSocket, or another local implementation chosen by Codex.

## Error shape

Expose structured errors containing at least:

```text
code
message
field_errors | null
```

Do not expose raw stack traces to the browser.
