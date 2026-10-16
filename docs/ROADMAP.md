# Future Product Roadmap

This is the single source for unimplemented product requirements. Current behavior is documented in [LOCAL_ARCHITECTURE.md](LOCAL_ARCHITECTURE.md), [UI_SPEC.md](UI_SPEC.md), and [API_SPEC.md](API_SPEC.md).

## Current foundation

Delivered: React/Vite/shadcn chat UI, NestJS chat/configuration API, PostgreSQL message/file persistence, collapsible titled chats, OpenAI key/model/thinking settings with online model discovery, OpenAI text replies using conversation history, response retry, local Docker Compose, generic Streamable HTTP MCP management/discovery/permissions and agent integration with explicit confirmation for state-changing tools. Separate standalone RAG (`rag-server/`) and synthetic manufacturing ML/MCP (`manufacturing-demo/`) services are implemented.

The application performs ordinary OpenAI text inference and can invoke explicitly permitted tools from connected MCP servers. It does not run ordered MCP workflows, analyze ordinary chat attachment contents, or validate answers. Future features must be requested/authorized step by step.

## Planned control plane

The eventual UI must let an operator:

1. Select registered external MCP servers for one or more ML services (registration/discovery/allowlisting already exist).
2. Select allowed tools for ordered ML steps; inspection and explicit read-only allowlisting are implemented.
3. Configure each step's input mappings and output name; reorder steps explicitly.
4. Register document references and associate them with an external RAG service/collection.
5. Configure an external RAG retrieval tool and its argument mappings.
6. Configure an external validator tool and its argument mappings.
7. Use the current OpenAI key/model/thinking configuration when implementing analyzer execution; add further provider/profile capabilities only when authorized.
8. Enter an operator prompt and run the selected workflow.
9. Inspect progress, ML outputs, RAG evidence, analyzer answer, validator result, errors, and timings.
10. Reopen completed execution records from persisted history.

Configuration and execution must be visibly distinct. core owns registry/configuration metadata; ordered workflow execution and full immutable run-trace persistence remain planned. External services continue to own ML, retrieval, validation, and domain-data implementations.

Every future password, API key, token, or confidential connection setting belongs in the root .env. UI/database profiles refer to named environment variables; secret values remain server-side and are excluded from API responses, browser storage, logs, and traces.

## Planned execution flow

~~~text
Operator prompt
→ ordered, explicitly mapped ML MCP calls
→ analyzer receives prompt + ML outputs + configured RAG context/tool access
→ configured RAG retrieval
→ analyzer candidate answer
→ external validator checks candidate answer/evidence
→ final answer, separate validator result, evidence, and full trace
~~~

No hidden step dependencies, domain-specific orchestration branches, or silent validator rewrites. An LLM statement is not retrieved evidence. Tool binding and safety rules are in [MCP_CONTRACTS.md](MCP_CONTRACTS.md).

## Planned run record

Every run must preserve:

- Operator prompt and selected workflow/version.
- Each MCP server/tool, sanitized arguments, normalized output or error, and call order.
- Start/end time and duration.
- Analyzer input-context summary and candidate answer.
- Retrieved RAG evidence.
- Validator inputs and result.
- Final displayed result.

A completed run's workflow version must remain inspectable even after configuration edits. Configuration and run-history schemas/routes will be specified when those features are authorized; no speculative endpoints/tables are part of the current API/schema.

## Future completion criteria

The orchestration phase is complete only when the operator can configure all external capabilities through the UI, run an ordered workflow, and inspect/reopen a complete trace. Mock MCP fixtures must demonstrate the end-to-end flow, and automated checks must cover mappings, allowlisting, errors, secret handling, evidence separation, validator order, and immutable run history.

This roadmap does not authorize cloud deployment or further external ML/validator/domain services. The user separately authorized the standalone RAG service; its current behavior is owned by `rag-server/README.md`. The fixed boundary is in [AGENTS.md](../AGENTS.md).

## Implemented task execution boundary

Persistent autonomous tasks, completion verification, retries, approvals, schedules, event triggers and task histories are now implemented; their specification is [TASK_EXECUTION.md](TASK_EXECUTION.md). The workflow configuration/mapping/validator research requirements above remain separate future work and are not a dependency for the task worker.
