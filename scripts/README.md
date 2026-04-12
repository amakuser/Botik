# Scripts

Stable scripts for the migrated new-stack path now live here.

Primary local desktop entry:

- `pwsh ./scripts/run-primary-desktop.ps1`
  Starts the frontend if needed, then launches the Tauri desktop shell.

Low-level development entrypoints:

- `pwsh ./scripts/dev-frontend.ps1`
- `pwsh ./scripts/dev-app-service.ps1`
- `pwsh ./scripts/dev-desktop.ps1`

Verification entrypoints:

- `pwsh ./scripts/generate-contracts.ps1`
- `pwsh ./scripts/check-forbidden-imports.ps1`
- `pwsh ./scripts/check-pr-template-rules.ps1`
- `pwsh ./scripts/test-unit.ps1`
- `pwsh ./scripts/test-integration.ps1`
- `pwsh ./scripts/test-e2e.ps1`
- `pwsh ./scripts/test-desktop-smoke.ps1`

Legacy launcher helpers have been retired from the supported operator flow.
Use git history or a pre-retirement commit only if deeper legacy fallback investigation is ever required.
