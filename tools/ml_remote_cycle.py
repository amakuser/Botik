"""
Local training workflow:
1) Pull SQLite DB from server.
2) Train locally (ml_service.run_loop --train-once).
3) Push active model artifact to server.
4) Activate model on server DB.
"""
from __future__ import annotations

import argparse
import json
import shlex
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


def _run(cmd: list[str]) -> None:
    print("RUN:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _ssh_base(port: int, identity_file: str | None) -> list[str]:
    base = ["ssh", "-p", str(port)]
    if identity_file:
        base.extend(["-i", identity_file])
    return base


def _scp_base(port: int, identity_file: str | None) -> list[str]:
    base = ["scp", "-P", str(port)]
    if identity_file:
        base.extend(["-i", identity_file])
    return base


def _read_active_model(db_path: Path) -> tuple[str, str, dict]:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT model_id, path_or_payload, metrics_json FROM model_registry WHERE is_active=1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise RuntimeError("No active model found in local DB after training.")

    model_id = row[0]
    model_path = row[1]
    metrics_raw = row[2] or "{}"
    metrics = json.loads(metrics_raw)
    return model_id, model_path, metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local ML cycle with remote sync.")
    parser.add_argument("--remote-user", required=True, help="Remote SSH user")
    parser.add_argument("--remote-host", required=True, help="Remote SSH host")
    parser.add_argument("--remote-repo-path", required=True, help="Absolute path to repo on server")
    parser.add_argument("--remote-python", default="python3", help="Python executable on server")
    parser.add_argument("--ssh-port", type=int, default=22, help="SSH port")
    parser.add_argument("--identity-file", default="", help="SSH private key path")
    parser.add_argument("--local-python", default=sys.executable, help="Local Python executable")
    parser.add_argument("--local-config", default="config.yaml", help="Local config path")
    parser.add_argument("--local-db-path", default="data/botik.db", help="Local DB path")
    args = parser.parse_args()

    identity_file = args.identity_file.strip() or None
    local_db_path = Path(args.local_db_path)
    local_db_path.parent.mkdir(parents=True, exist_ok=True)

    remote = f"{args.remote_user}@{args.remote_host}"
    remote_db = f"{args.remote_repo_path.rstrip('/')}/data/botik.db"

    # 1) Pull DB from server.
    pull_cmd = _scp_base(args.ssh_port, identity_file) + [f"{remote}:{remote_db}", str(local_db_path)]
    _run(pull_cmd)

    # 2) Train locally.
    train_cmd = [args.local_python, "-m", "ml_service.run_loop", "--train-once", "--config", args.local_config]
    _run(train_cmd)

    # 3) Read active model and push artifact/metrics.
    model_id, model_path, metrics = _read_active_model(local_db_path)
    local_model_path = Path(model_path)
    if not local_model_path.exists():
        raise FileNotFoundError(f"Model artifact not found: {local_model_path}")

    model_path_unix = model_path.replace("\\", "/")
    remote_model_path = f"{args.remote_repo_path.rstrip('/')}/{model_path_unix}"
    remote_model_dir = str(Path(remote_model_path).parent).replace("\\", "/")
    remote_metrics_path = f"{args.remote_repo_path.rstrip('/')}/data/models/{model_id}.metrics.json"

    mkdir_cmd = _ssh_base(args.ssh_port, identity_file) + [remote, f"mkdir -p {shlex.quote(remote_model_dir)}"]
    _run(mkdir_cmd)

    push_model_cmd = _scp_base(args.ssh_port, identity_file) + [str(local_model_path), f"{remote}:{remote_model_path}"]
    _run(push_model_cmd)

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8") as tmp:
        json.dump(metrics, tmp, ensure_ascii=False, indent=2)
        metrics_file = tmp.name

    push_metrics_cmd = _scp_base(args.ssh_port, identity_file) + [metrics_file, f"{remote}:{remote_metrics_path}"]
    _run(push_metrics_cmd)

    # 4) Activate model on server DB.
    promote_cmd_str = " && ".join(
        [
            f"cd {shlex.quote(args.remote_repo_path)}",
            " ".join(
                [
                    shlex.quote(args.remote_python),
                    "tools/promote_model.py",
                    "--db-path",
                    "data/botik.db",
                    "--model-id",
                    shlex.quote(model_id),
                    "--model-path",
                    shlex.quote(model_path_unix),
                    "--metrics-file",
                    shlex.quote(remote_metrics_path),
                ]
            ),
        ]
    )
    promote_cmd = _ssh_base(args.ssh_port, identity_file) + [remote, promote_cmd_str]
    _run(promote_cmd)

    print(
        f"ML_REMOTE_CYCLE_OK model_id={model_id} "
        f"model_path={model_path} remote_host={args.remote_host}"
    )


if __name__ == "__main__":
    main()
