# ADR-004: Job Manager Ownership

- Status: Accepted

## Context

Background work is currently launched through multiple paths and owners. This creates operational drift, console window issues, weak cleanup behavior, and hard-to-test flows.

## Decision

All user-facing background jobs will be owned only by a single Job Manager layer.

The frontend and desktop shell are forbidden from launching business subprocesses directly.

## Consequences

Positive:

- one source of truth for process lifecycle;
- fewer zombie and orphaned processes;
- consistent hidden-window launch policy;
- clearer observability and cleanup logic;
- reusable lifecycle tests.

Negative:

- requires introducing job definitions and a registry;
- current ad-hoc process paths must eventually be routed through the new owner.

## Rejected Alternatives

- Let each screen launch its own subprocess:
  - rejected because it recreates current chaos.
- Keep multiple process managers by feature:
  - rejected because ownership drift returns quickly.

## Implications for Tests and Agents

- agents can start, observe, and stop work through one stable interface;
- tests can assert status and cleanup without shell scraping;
- visible console windows are no longer part of normal flow.
