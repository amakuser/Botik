# Botik Architecture Foundation

This directory locks in the Stage 1 architecture for the next-generation Botik desktop application.

Stage 1 does not rewrite the existing product. It establishes:

- the target architecture for the long-term platform;
- the process and job lifecycle model;
- the permanent testing platform;
- the migration phases and rollback expectations;
- the architectural constraints that future work must respect.

## Scope

The current production UI remains in place during Stage 1. The new foundation is introduced alongside it and is expected to prove itself through a single vertical slice before broader migration starts.

## Non-Negotiable Constraints

- No big bang rewrite.
- No system mouse or focus-stealing automation as the main testing strategy.
- No visible console windows as a normal part of app or test execution.
- Test tooling is a permanent platform subsystem, not one-off project glue.
- Background jobs are owned only by the future Job Manager layer.

## Target Layering

```text
Frontend (Vite + React + TypeScript)
  -> Typed App Client
  -> App Service (FastAPI, HTTP + SSE)
  -> Job Manager / Supervisor
  -> Python Workers / Runtimes
  -> Structured Logs / Progress / Status / Errors
```

## Key Documents

- [Process lifecycle](./process-lifecycle.md)
- [ADR index](./adrs/)
- [Testing strategy](../testing/testing-strategy.md)
- [Development workflow](../dev-workflow/development-workflow.md)
- [Migration rollback plan](../migration/rollback-plan.md)
- [Minimal CI plan](../ci/minimal-ci-plan.md)

## Stage 1 Outputs

Stage 1 is complete only when the repository contains:

- architecture decision records for the major platform choices;
- a permanent testing strategy and selector contract;
- a documented process lifecycle model;
- a migration plan with rollback rules;
- scaffold directories for the new foundation;
- no large-scale rewrite of the current application path.
