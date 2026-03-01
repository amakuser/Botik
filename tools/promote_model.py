"""
Promote a trained model in model_registry on the target host.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from src.botik.storage.sqlite_store import get_connection, upsert_model_registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote model in model_registry")
    parser.add_argument("--db-path", default="data/botik.db", help="SQLite database path")
    parser.add_argument("--model-id", required=True, help="Model id")
    parser.add_argument("--model-path", required=True, help="Path to model artifact relative to repo root")
    parser.add_argument("--metrics-file", required=True, help="Path to JSON metrics file")
    args = parser.parse_args()

    with open(args.metrics_file, encoding="utf-8") as f:
        metrics = json.load(f)

    conn = get_connection(args.db_path)
    try:
        upsert_model_registry(
            conn,
            model_id=args.model_id,
            path_or_payload=args.model_path,
            metrics_json=json.dumps(metrics, ensure_ascii=False),
            created_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            is_active=True,
        )
    finally:
        conn.close()

    print(f"PROMOTED model_id={args.model_id} model_path={args.model_path}")


if __name__ == "__main__":
    main()
