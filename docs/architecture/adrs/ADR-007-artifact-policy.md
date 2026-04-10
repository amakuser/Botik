# ADR-007: Artifact Policy

- Status: Accepted

## Context

When E2E or desktop smoke tests fail, diagnosis must not depend on rerunning the scenario manually while watching the screen.

## Decision

Critical-path test failures must retain:

- screenshot;
- Playwright trace;
- HTML report;
- structured app-service log;
- job-specific log;
- process cleanup summary.

Trace capture should be optimized for cost:

- screenshot on failure;
- trace on first retry or equivalent low-overhead policy;
- video only if later justified for a specific class of failures.

## Consequences

Positive:

- failures are inspectable without re-running under observation;
- CI can preserve actionable artifacts;
- agents can use the same diagnostic outputs as human maintainers.

Negative:

- artifact storage and pruning policies are needed;
- log formats must be standardized.

## Rejected Alternatives

- Manual repro as the normal debugging path:
  - rejected because it is too slow and not reliable for future automation.

## Implications for Tests and Agents

- artifacts become part of the platform, not optional extras;
- future agent workflows can diagnose failures without touching the user session.
