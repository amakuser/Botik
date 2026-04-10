# ADR-008: Migration and Rollback Strategy

- Status: Accepted

## Context

The product cannot tolerate a big bang rewrite. The new architecture must prove itself gradually while preserving a safe rollback path.

## Decision

Migration will proceed in phases:

- Foundation
- Vertical Slice
- Stabilization
- Feature Migration
- Legacy Removal

Each migrated surface must be independently rollbackable while the legacy path remains available.

## Consequences

Positive:

- risk is contained by feature area;
- architectural validation happens before broad migration;
- rollback is possible without abandoning the entire foundation.

Negative:

- temporary coexistence of old and new layers;
- requires discipline around feature flags or route switching.

## Rejected Alternatives

- Big bang replacement of the current UI:
  - rejected because it is high-risk and hard to stabilize.
- Rewrite without rollback planning:
  - rejected because recovery from migration regressions would be too expensive.

## Implications for Tests and Agents

- the same permanent test tooling can validate both new slices and rollback behavior;
- agents get a safer migration environment with predictable fallback paths.
