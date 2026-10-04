# Files in this revised local-only specification

This bundle replaces the earlier AWS-oriented specification for the current phase.

## Created/replaced

- `AGENTS.md`
- `CODEX_IMPLEMENTATION_TASK.md`
- `.env.example`
- `.codex/skills/meta-harness-ui/SKILL.md`
- `docs/LOCAL_ARCHITECTURE.md`
- `docs/UI_SPEC.md`
- `docs/DATA_MODELS.md`
- `docs/API_SPEC.md`
- `docs/MCP_CONTRACTS.md`
- `docs/ACCEPTANCE_TESTS.md`
- `docs/IMPLEMENTATION_DECISIONS.md`
- `docs/FILES_EDITED.md`

## Explicitly removed from the previous direction

- AWS architecture requirements
- Terraform requirements
- Lambda/DynamoDB/EventBridge/SQS/Fargate design
- Amazon OpenSearch requirement
- production BGP tool implementations
- production RAG implementation
- production validator implementation

The phase now focuses only on the local microservice-ready main meta-harness UI/control plane and generic MCP orchestration.
