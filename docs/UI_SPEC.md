# UI Specification

The UI is the main deliverable of this phase.

## Navigation

Provide these primary areas:

1. **MCP Registry**
2. **Workflow Builder**
3. **Knowledge / RAG**
4. **Analyzer**
5. **Operator Console**
6. **Run History**

The exact visual framework and component library are implementation decisions delegated to Codex.

## 1. MCP Registry

Purpose: register external microservices exposed through MCP.

A server form must include:

- display name;
- capability category: `ML`, `RAG`, `VALIDATOR`, or `OTHER_READ_ONLY`;
- MCP endpoint/connection configuration;
- enabled/disabled state;
- optional non-secret metadata/tags.

Secret values must be referenced through backend/environment configuration rather than persisted in browser storage.

Actions:

- Add server
- Edit server
- Delete server
- Test connection
- Refresh/introspect tools
- View discovered tool names and input schemas

A tool is never executable by a workflow unless the operator explicitly selects/allowlists it.

## 2. Workflow Builder

Purpose: define the ordered preprocessing/enrichment chain before the analyzer.

The operator can:

- create a workflow;
- rename it;
- add an ML step from an allowlisted MCP tool;
- add multiple ML steps;
- reorder steps by drag/drop or explicit move controls;
- enable/disable a step;
- define an output name for each step;
- define input mapping for each tool argument;
- save a versioned workflow;
- duplicate a workflow;
- view validation errors before save/run.

Supported input mapping sources:

- operator prompt;
- static literal value;
- run metadata;
- prior step output by output name;
- prior step selected field/path.

Do not infer mappings silently.

Show a simple flow visualization of the configured order.

## 3. Knowledge / RAG

Purpose: configure the relationship between documents and an external RAG service.

### RAG configuration

The operator selects:

- one registered `RAG` MCP server;
- one allowlisted retrieval/search tool;
- optional ingest/register tool if exposed by that server;
- collection/index/profile identifier used by that RAG service.

The main application does not implement embeddings, chunking, vector storage, ranking, or reranking.

### Documents

The UI lets the user register documents with:

- title/name;
- local file selection or local path/URI metadata;
- tags;
- description;
- assigned RAG server;
- assigned collection/index/profile;
- optional relation labels such as `system_documentation`, `policy`, `past_incident`, `runbook`, `other`.

The core stores document metadata and the relationship to the RAG configuration.

If the selected RAG MCP exposes an ingestion tool, the UI may invoke it explicitly when the operator clicks an ingest/register action. Do not implement ingestion internally.

Display ingestion/registration result when available.

## 4. Analyzer

Provide configuration for the central analyzer profile.

At minimum:

- profile name;
- provider/adapter;
- model identifier;
- system/investigator instruction text;
- enabled RAG access yes/no;
- selected RAG profile;
- response format preference if supported by the adapter.

Do not store API secrets in the browser.

## 5. Validator configuration

Validator setup may appear in Workflow Builder or a dedicated panel.

The operator selects:

- one registered `VALIDATOR` MCP server;
- one allowlisted validation tool;
- explicit mappings from candidate answer/context/evidence to validator arguments.

The validator runs after the analyzer candidate answer in v1.

The validator result is displayed separately from the analyzer answer.

The validator does not automatically rewrite the answer.

## 6. Operator Console

The console must contain:

- workflow selector;
- analyzer profile selector;
- multiline prompt/question input;
- Run button;
- Cancel button if the local execution engine supports cancellation;
- live/refreshing execution timeline;
- final result view.

The execution timeline shows in order:

- step number;
- step type;
- MCP server;
- tool name;
- status;
- duration;
- request summary;
- response summary/error.

The final result area must separately show:

- analyzer answer;
- retrieved RAG evidence;
- validator result;
- overall run status;
- complete trace/audit view.

## 7. Run History

Show prior runs with:

- run ID;
- timestamp;
- workflow/version;
- short prompt preview;
- status;
- duration;
- validator outcome when present.

Opening a run shows the immutable execution trace captured for that run.
