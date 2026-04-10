from pathlib import Path


class LegacyRuntimeAdapter:
    """Boundary adapter for the existing Botik runtime.

    Phase A keeps the legacy runtime untouched. This adapter is the future place
    where app-service jobs will call into the existing Python entrypoints.
    """

    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[4]
