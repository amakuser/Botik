# Artifact Retention Strategy

This document defines how test artifacts are retained for local runs and CI.

## Core Rule

Critical-path failures must emit enough artifacts to debug without rerunning the scenario interactively.

Required artifacts:

- screenshot;
- Playwright trace;
- HTML report;
- structured app-service log;
- per-job log when relevant;
- process cleanup summary.

## Local Development

Local artifacts live under:

- `.artifacts/local/latest/`
- `.artifacts/local/history/`

Policy:

- overwrite `latest` on each run;
- keep timestamped failed runs in `history`;
- auto-prune local history to the latest 20 failed runs.

## CI Pull Requests

Policy:

- keep failed E2E and desktop-smoke artifacts for 14 days;
- keep screenshots only on failure;
- keep traces on first retry or equivalent low-overhead mode.

## CI Main and Nightly

Policy:

- keep retained artifacts for 30 days.

## Release Branches and Tags

Policy:

- keep packaging and smoke artifacts for 60 days.

## Logging Expectations

Artifacts are incomplete without:

- structured service logs;
- job logs for the scenario under test;
- explicit cleanup results for child processes.

## Cleanup Summary

Cleanup artifacts should report:

- started process ids if known;
- stop outcome;
- whether a graceful stop succeeded;
- whether a forced tree kill was required;
- whether any orphaned child was detected.
