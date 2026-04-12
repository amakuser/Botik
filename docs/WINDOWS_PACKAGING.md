# Windows Packaging

## What is built

- Primary GUI/product path: the Tauri desktop shell from `apps/desktop`.
- Supported packaged outputs on current `master`:
  - MSI bundle
  - NSIS setup bundle
- The old PyInstaller/Inno fallback packaging path has been retired.

## Entrypoints

- Source/dev primary GUI: `pwsh ./scripts/run-primary-desktop.ps1`
- Source/dev shell-only: `pwsh ./scripts/dev-desktop.ps1`
- Packaged primary GUI: `corepack pnpm --dir ./apps/desktop build`

Important:

- the supported packaged GUI path is the Tauri shell only;
- rollback after legacy retirement happens through git history or PR revert, not through a supported fallback EXE/installer path;
- some internal legacy modules may still remain in the repository for compatibility/test cleanup, but they are not a supported packaging target.

## Build locally

Primary shell build:

```bat
corepack pnpm --dir apps/desktop build
```

Primary source/dev launch:

```bat
pwsh ./scripts/run-primary-desktop.ps1
```

Bundle outputs:

```text
apps\desktop\src-tauri\target\release\bundle\msi\
apps\desktop\src-tauri\target\release\bundle\nsis\
```

## Runtime/logs

- The Tauri desktop shell owns GUI startup and managed app-service lifecycle for the migrated product path.
- Desktop shell artifacts and logs are written under `.artifacts/local/...` in source/dev and test runs.
- Frontend/app-service local verification remains covered by the permanent test platform.

## Source mode vs packaged mode

- Primary source/dev mode:
  - `pwsh ./scripts/run-primary-desktop.ps1`
  - `pwsh ./scripts/dev-app-service.ps1`
  - `pwsh ./scripts/dev-frontend.ps1`
- Primary packaged mode:
  - `corepack pnpm --dir ./apps/desktop build`

## Update behavior

- In source/git mode, Telegram `/update` uses git and updates `version.txt`.
- In packaged mode (no `.git`), `/update` returns `repo_unavailable` and reports current `version.txt`.
  - Upgrade path in packaged mode is: install a newer Tauri desktop bundle.

## Notes

- If a code-signing certificate is available, sign the Tauri desktop artifacts produced by the primary packaging flow.
- See [docs/migration/legacy-retirement.md](migration/legacy-retirement.md) for the exact retirement boundary.
