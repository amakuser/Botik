# Desktop Shell

This directory contains the Tauri desktop shell that is now the primary GUI/product path for the migrated Botik stack.

Current shell ownership:

- window lifecycle;
- managed app-service startup and shutdown;
- runtime-config injection into the frontend;
- packaging integration for the new-stack desktop app.

The shell does not own:

- business job orchestration;
- runtime control policy;
- trading or training subprocess launch logic from the UI.

Useful commands:

- primary local desktop entry: `pwsh ./scripts/run-primary-desktop.ps1`
- low-level shell-only launch: `pwsh ./scripts/dev-desktop.ps1`
- packaged shell build: `corepack pnpm --dir ./apps/desktop build`

The old pywebview path is no longer a supported operator or packaging path.
Internal legacy modules may still remain in the repository for compatibility/test cleanup, but the supported desktop path is the Tauri shell only.
