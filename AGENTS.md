# Local Meta-Harness — Codex Engineering Contract

## Role

You are the implementation engineer for this repository.

The user owns the research goal and the high-level product boundary. You own normal software-design and implementation decisions inside that boundary.

Do not ask the user to choose routine implementation details. Choose sound defaults, keep the design maintainable, and record non-trivial choices in `docs/IMPLEMENTATION_DECISIONS.md`.

## Fixed product boundary

This phase is LOCAL ONLY.

Do not implement AWS, Terraform, Kubernetes, cloud queues, serverless functions, managed vector databases, or production deployment infrastructure.

The complete future system is microservice-oriented, but this phase implements only the local MAIN META-HARNESS application:

1. a web UI/control plane;
2. the minimal local backend/orchestration service required for that UI to work;
3. MCP client integration used to connect to external microservices.

The following are EXTERNAL microservices and MUST NOT be implemented in this repository:

- ML model services;
- RAG/vector-search server;
- deterministic validator implementation;
- BGP/domain-data providers;
- any other domain-specific MCP server.

They are represented only by MCP connections and tool contracts entered/configured through the UI.

## Purpose of the main application

The application lets an operator configure and use a meta-harness around an LLM analyzer without hard-coding individual ML, RAG, or validator implementations.

The UI must let the user:

1. register MCP servers for one or more ML models;
2. select the MCP tools exposed by those ML services;
3. define the order in which the ML tools are called;
4. register documents and associate them with a configured RAG service/collection;
5. register a RAG MCP server and select its search/retrieval tool;
6. register a validator MCP server and select its validation tool;
7. configure the analyzer/LLM used by the main harness;
8. enter an operator prompt/question;
9. run the configured workflow;
10. inspect the execution trace, retrieved evidence, analyzer answer, and validator result.

## Runtime model

The main application is a generic orchestrator.

The configured runtime flow is:

Operator prompt
→ ordered ML MCP calls
→ analyzer receives prompt + ML outputs + available RAG context/tool access
→ RAG MCP retrieval as configured
→ analyzer produces a candidate answer
→ validator MCP checks the candidate answer/evidence
→ final result and trace shown to the operator

The application must not contain BGP-specific branching in its orchestration core.

## Microservice boundary

Implement these local services:

### `ui`

Browser-facing control-plane UI.

### `core`

Local API/orchestrator used by the UI. It owns:

- MCP server registry;
- workflow configuration;
- document-to-RAG mapping metadata;
- analyzer configuration;
- workflow execution;
- execution tracing;
- local persistence of configuration and run history.

Do not implement ML, RAG, or validator server logic inside `core`.

The external services are independently deployable MCP servers configured by URL/connection details.

## Codex autonomy

You SHOULD decide implementation-level details yourself, including:

- frontend framework;
- backend framework;
- module/package structure;
- component decomposition;
- local persistence technology;
- dependency injection pattern;
- HTTP/MCP client library;
- state-management library;
- form library;
- schema-validation library;
- test framework details;
- retry/error-handling implementation;
- internal API organization;
- visual component library;
- logging implementation;
- Dockerfile layout;
- local development tooling.

Prefer simple, common, maintainable choices.

## When to ask the user

Ask only when a decision would change one of these high-level requirements:

- local-only scope;
- microservice boundary;
- which categories of external services exist;
- operator-visible workflow behavior;
- read-only safety boundary for connected operational data;
- research/evaluation scope;
- whether this repository should start implementing an external ML/RAG/validator service.

Do not ask about ordinary library, class, file, database, UI-component, or design-pattern choices.

## MCP principles

Treat MCP servers as capabilities, not as hard-coded vendors.

The core must not contain branches such as `if server_name == ...`.

A configured MCP tool is identified through registry/configuration metadata and invoked through a generic MCP client abstraction.

MCP failures must be visible in the run trace and must not crash the entire application process.

Secrets/tokens must never be stored in browser local storage or committed to source control.

## Workflow principles

The user controls the order of ML MCP steps through the UI.

Each step has explicit input mapping and output naming so later steps can consume earlier results.

Do not infer hidden dependencies between steps.

The analyzer step is the central reasoning step. The validator step checks the candidate answer; it does not silently rewrite the answer.

Every run must be inspectable after completion.

## Evidence and traceability

For every workflow run, preserve:

- operator prompt;
- selected workflow/version;
- each MCP server/tool called;
- sanitized tool arguments;
- normalized tool result or error;
- call order;
- start/end time and duration;
- analyzer input context summary;
- analyzer answer;
- RAG evidence returned;
- validator input and result;
- final displayed result.

Do not treat an LLM-generated statement as retrieved evidence.

## Safety

Connected domain/data tools are read-only in this phase.

The UI must clearly distinguish configuration from execution.

Do not provide any generic arbitrary-shell or arbitrary-code-execution feature.

Do not auto-discover and execute tools without operator-configured allowlisting.

## Required specification files

Read before implementation:

1. `docs/LOCAL_ARCHITECTURE.md`
2. `docs/UI_SPEC.md`
3. `docs/DATA_MODELS.md`
4. `docs/API_SPEC.md`
5. `docs/MCP_CONTRACTS.md`
6. `docs/ACCEPTANCE_TESTS.md`

Where those files leave a low-level implementation choice open, decide it yourself.

## Definition of done

The phase is complete when:

- the local UI and core services start locally;
- the user can register MCP servers;
- MCP tools can be inspected/selected;
- ML steps can be ordered and configured;
- documents can be mapped to a RAG MCP/collection;
- validator MCP/tool can be configured;
- the operator can enter a prompt and run a workflow;
- a full execution trace is shown;
- mock MCP servers can demonstrate the end-to-end UI flow;
- automated tests pass;
- no AWS/cloud implementation exists;
- no ML model, RAG engine, or validator business logic is implemented in this repository.
