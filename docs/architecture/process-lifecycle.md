# Process Lifecycle

This document defines the future ownership and lifecycle rules for user-facing background jobs in Botik.

## Core Decision

All user-facing background processes must be owned by a single `Job Manager` layer.

The following layers are not allowed to launch or supervise business jobs directly:

- frontend UI;
- desktop shell;
- ad-hoc feature modules;
- one-off scripts triggered from tabs or page actions.

## Why This Exists

The current application has multiple process owners and launch paths. That creates:

- inconsistent runtime behavior;
- zombie and orphaned child processes;
- console window flashes;
- weak observability;
- test fragility;
- increasing architectural drift over time.

## Process Ownership Model

```text
UI command
  -> App Service endpoint
  -> Job Manager
  -> Worker launcher
  -> Managed child process tree
  -> Structured events/logs/progress back to App Service/UI
```

## Responsibilities

### App Service

- validates commands and inputs;
- translates UI commands into job requests;
- exposes job status and event streams;
- never directly supervises process trees outside the Job Manager boundary.

### Job Manager

- owns job registry and job definitions;
- starts processes;
- stops processes gracefully;
- restarts processes only when policy allows it;
- captures stdout and stderr;
- emits structured progress and log events;
- marks jobs as completed, failed, cancelled, or orphaned;
- performs cleanup on shutdown or crash recovery.

### Worker

- executes a single business responsibility;
- exposes logs and progress through stdout/stderr or structured side channels;
- does not know about the UI or shell.

## Required Job States

- `queued`
- `starting`
- `running`
- `stopping`
- `completed`
- `failed`
- `cancelled`
- `orphaned`

## Required Job Fields

- `job_id`
- `job_type`
- `state`
- `progress`
- `started_at`
- `updated_at`
- `exit_code`
- `restart_policy`
- `last_error`
- `log_stream_id`

## Required Runtime Guarantees

- Windows child processes must launch with hidden-window policy.
- `stdout` and `stderr` must be captured programmatically.
- No ordinary job execution may rely on visible `cmd.exe` or terminal windows.
- Job stop sequence must be:
  1. graceful stop signal;
  2. bounded timeout;
  3. hard kill of the process tree if needed.
- The default restart policy is `never`.
- Orphan and zombie process detection is mandatory after application crash or interrupted tests.

## Observability

Every job must be observable through the app-service layer without scraping the screen.

Minimum observability:

- status endpoint;
- progress value;
- live log stream;
- error payload;
- retained log history;
- cleanup outcome.

## Testing Implications

The lifecycle model must support:

- headless start/stop/status verification;
- artifact collection on failure;
- assertions that no visible console windows are required;
- assertions that cleanup completed successfully.
