# Data Models

These are logical models. Codex may implement them using the chosen backend/schema library while preserving the fields and relationships.

## MCPServerConfig

```text
id
name
category: ML | RAG | VALIDATOR | OTHER_READ_ONLY
transport
endpoint
secret_ref | null
enabled
metadata
created_at
updated_at
```

Do not persist raw secret values in this model.

## MCPToolDescriptor

```text
server_id
tool_name
description
input_schema
last_discovered_at
allowlisted
```

## Workflow

```text
id
name
version
steps: ordered list[WorkflowStep]
enabled
created_at
updated_at
```

## WorkflowStep

```text
id
position
name
server_id
tool_name
enabled
input_mappings: map[tool_argument, InputMapping]
output_name
```

## InputMapping

```text
source_type: OPERATOR_PROMPT | STATIC | RUN_METADATA | PRIOR_STEP | PRIOR_STEP_FIELD
source_ref | null
value | null
```

## DocumentRecord

```text
id
title
local_reference
content_sha256 | null
description | null
tags: list[str]
relation_label
rag_server_id
rag_collection
status
created_at
updated_at
```

`local_reference` is metadata about where the document was selected/staged locally. Do not assume the RAG service can directly access it.

## RAGProfile

```text
id
name
server_id
retrieval_tool
ingest_tool | null
collection
retrieval_argument_mappings
created_at
updated_at
```

## AnalyzerProfile

```text
id
name
adapter
model
instructions
enable_rag
rag_profile_id | null
response_format | null
created_at
updated_at
```

## ValidatorProfile

```text
id
name
server_id
tool_name
input_mappings
created_at
updated_at
```

## RunRecord

```text
id
workflow_id
workflow_version
analyzer_profile_id
validator_profile_id | null
operator_prompt
status: PENDING | RUNNING | COMPLETED | FAILED | CANCELLED
started_at
finished_at | null
analyzer_answer | null
validator_result | null
error_summary | null
```

## StepTrace

```text
id
run_id
sequence
kind: ML_MCP | RAG_MCP | ANALYZER | VALIDATOR_MCP
server_id | null
tool_name | null
started_at
finished_at
status: RUNNING | SUCCESS | ERROR | SKIPPED
sanitized_input
normalized_output | null
error | null
output_name | null
```

## EvidenceItem

```text
id
run_id
source_kind: RAG | MCP_TOOL | DOCUMENT | OTHER
source_ref
summary
payload_or_reference
created_at
```

LLM-generated text is not an EvidenceItem unless it is explicitly stored as model output with `source_kind=OTHER`; it must never be labeled as retrieved evidence.
