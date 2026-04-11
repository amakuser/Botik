# Rollback Plan

This document defines how the migration remains reversible while the new foundation proves itself.

## Core Rule

The current production path remains available until the new foundation has demonstrated parity for the migrated surface and the test platform has validated it.

## Rollback Model by Phase

### Foundation

Rollback:

- disable new foundation entrypoints;
- keep the legacy UI as the only active product path.

Reason:

- no user-facing replacement should depend on unfinished scaffolding.

### Vertical Slice

Rollback:

- switch the migrated slice back to the legacy route or feature path;
- keep the foundation and test tooling in the repository.

Reason:

- shared platform work is not rolled back just because one slice is unstable.

### Stabilization

Rollback:

- do not roll back the testing platform itself;
- roll back unstable slices or features instead.

Reason:

- test tooling is a permanent subsystem and should not be treated as disposable.

### Feature Migration

Rollback:

- rollback per migrated surface;
- do not revert the whole foundation unless the platform itself is invalidated.

Reason:

- migrations should be isolated and reversible by feature area.

### Primary Path Cutover

Rollback:

- switch the documented and operator-default GUI path back to the legacy launcher;
- keep the migrated new-stack routes and services in the repository;
- keep the Tauri shell available for continued validation, but not as the default path.

Reason:

- cutover should be reversible without deleting either implementation path.

### Legacy Removal

Rollback:

- only possible before final legacy removal cutover;
- create a stable tag or branch before removing the old primary path.

## Route and Feature Switching

During coexistence, migrated areas should be independently switchable between:

- `legacy`
- `next`

This switch should come from configuration, manifest, or app-service capability response rather than manual code editing in production workflows.

## Testing Requirement for Rollback

Rollback safety is incomplete unless:

- the migrated path has automated tests;
- the fallback path is still operational;
- artifacts can show why the migrated path was rolled back.
