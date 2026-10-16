# Execution Plans

Use an ExecPlan for significant implementation work: new major components, changes across modules, architecture/schema changes, external integrations, or orchestration changes.

Place active plans in docs/plans/. Keep them updated while work is in progress. When a plan is complete, preserve current design choices in docs/IMPLEMENTATION_DECISIONS.md and relevant behavior in the owning specification; remove the redundant completed plan.

Each plan must contain:

## Goal

The authorized outcome and its current/future product scope.

## Motivation

Why the change is needed.

## Existing architecture

Affected services/modules and their present behavior.

## Proposed design

Interfaces, data flow, schema changes, and significant decisions. Preserve the boundaries in AGENTS.md.

## Implementation steps

Concrete order of work and any migration/compatibility steps.

## Validation

How correctness will be demonstrated. Separate automated checks from manual/API/browser review. UI work requires screenshots compared with the user's reference.

## Evaluation impact

Whether research metrics or baselines are affected; use “none” for changes without evaluation impact.

## Risks

Concrete compatibility, persistence, security, and operational risks.
