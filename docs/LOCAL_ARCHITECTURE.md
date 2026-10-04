# Local Architecture

## Goal

Build a local microservice-oriented control plane for configuring and running a generic LLM meta-harness.

The main application does not own ML, RAG, or validator logic. It connects to those capabilities through MCP.

## Services implemented in this repository

```text
Browser
   |
   v
+------------------+
| UI service       |
| Control plane    |
+--------+---------+
         |
         | local HTTP API
         v
+----------------------------+
| Core service               |
|                            |
| - MCP registry             |
| - Workflow definitions     |
| - Analyzer adapter         |
| - Generic MCP client       |
| - Workflow runner          |
| - Run/evidence trace       |
| - Local persistence        |
+------+----------+-----------+
       |          |
       | MCP      | MCP
       v          v
+-----------+   +-----------+       +--------------+
| ML MCP(s) |   | RAG MCP   |       | Validator MCP|
| external  |   | external  |       | external     |
+-----------+   +-----------+       +--------------+
```

ML/RAG/Validator services are external and are not implemented here.

## Local deployment

Use local containers for `ui` and `core`.

The repository should provide one local startup command, preferably through Docker Compose, that starts the implemented services.

External MCP services are configured by endpoint through the UI and are not part of the required compose stack.

## Main design properties

### Harness-agnostic

The orchestration engine operates on configured capabilities and tool schemas rather than provider-specific code paths.

### Microservice-compatible

All external capabilities are addressed through explicit service boundaries. No ML/RAG/validator implementation is linked directly as an in-process library.

### Locally inspectable

Every configuration and run can be inspected without cloud dependencies.

### Replaceable services

Replacing an ML model, RAG server, or validator should require configuration changes, not changes to orchestration-core source code.

## Runtime sequence

For one operator question:

```text
Operator Prompt
      |
      v
Ordered ML MCP steps
      |
      v
Accumulated execution context
      |
      +------> RAG MCP retrieval/context
      |
      v
Analyzer / LLM
      |
      v
Candidate answer + evidence references
      |
      v
Validator MCP
      |
      v
Operator result + full trace
```

## Analyzer

The analyzer is an adapter behind a stable interface.

The initial implementation may use an OpenAI/Codex-compatible analyzer, but orchestration code must depend on an analyzer interface rather than a concrete model/provider.

The analyzer must receive only the workflow context intentionally assembled by the core.

## Persistence

Persist locally:

- MCP server configurations;
- selected tools;
- workflows and step order;
- document metadata and RAG mappings;
- analyzer profiles without secret values;
- run records;
- step traces;
- validator results.

Codex may choose the local persistence implementation.

## Out of scope

- production authentication/SSO;
- cloud deployment;
- horizontal scaling;
- event buses/queues;
- production secrets manager;
- implementation of ML/RAG/validator microservices;
- production BGP/network integrations.
