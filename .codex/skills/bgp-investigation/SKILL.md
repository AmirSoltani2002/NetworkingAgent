---
name: bgp-investigation
description: Investigate a BGP alert by gathering evidence, testing competing hypotheses, running deterministic checks, and producing a traceable operator report.
---

# BGP investigation workflow

Use this skill when implementing or testing the runtime investigation
workflow for a BGP alert.

## Investigation loop

Start from the alert and extracted structured features.

Create one or more hypotheses, for example:

- legitimate routing change
- route leak
- prefix hijack
- sub-prefix hijack
- DDoS mitigation
- anycast change
- configuration error
- insufficient evidence

For each hypothesis:

1. determine which evidence would support or contradict it,
2. query appropriate read-only tools,
3. record returned evidence,
4. run applicable deterministic validators,
5. update hypothesis confidence,
6. decide whether more evidence is needed.

Stop when:

- sufficient evidence supports a conclusion,
- investigation budget is exhausted, or
- further evidence cannot resolve the ambiguity.

Never fabricate missing evidence.

## Retrieval versus tools

RAG retrieves contextual knowledge such as:

- network documentation
- operator policies
- known customers
- previous incidents
- planned changes
- known benign patterns

Live tools retrieve current or historical observations such as:

- BGP updates
- route history
- RPKI state
- AS relationships
- traceroutes
- registry information

Do not treat these as equivalent sources.

## Validation

Deterministic validators verify factual or rule-based properties.

They do not ask another LLM whether the first LLM is correct.

## Reporting

Return:

- verdict
- confidence
- hypotheses
- evidence
- validation results
- contradictions
- unresolved questions
- suggested operator action

Every factual conclusion must reference evidence IDs.
