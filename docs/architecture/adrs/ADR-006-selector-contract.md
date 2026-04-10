# ADR-006: Selector Contract

- Status: Accepted

## Context

Long-term UI automation requires selectors that survive refactors and do not depend on layout coordinates or incidental structure.

## Decision

Selector priority is:

1. role
2. label
3. stable semantic text
4. data-testid

When `data-testid` is needed, its format must be:

`screen.entity.action`

## Consequences

Positive:

- accessible and testable UI patterns are encouraged;
- selectors remain stable across styling changes;
- tests become easier for both humans and agents to reason about.

Negative:

- requires product teams to think about testability during implementation;
- some complex UI widgets still need explicit test ids.

## Rejected Alternatives

- coordinate-based selectors:
  - rejected because they are fragile and user-session dependent.
- arbitrary CSS selectors:
  - rejected because they are too coupled to markup structure.

## Implications for Tests and Agents

- selectors become a documented product contract;
- future agents can safely navigate features without relying on screenshots or active desktop focus.
