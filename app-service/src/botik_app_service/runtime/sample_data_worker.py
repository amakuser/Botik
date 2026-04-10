import argparse
import csv
import json
import sys
import time
from pathlib import Path


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--sleep-ms", type=int, default=80)
    args = parser.parse_args()

    input_path = Path(args.input)
    rows = list(csv.DictReader(input_path.read_text(encoding="utf-8").splitlines()))
    total = max(len(rows), 1)
    sleep_seconds = max(args.sleep_ms, 20) / 1000

    _emit(
        {
            "type": "log",
            "level": "INFO",
            "message": f"Starting sample data import for {total} rows.",
        }
    )

    for index, row in enumerate(rows, start=1):
        symbol = row.get("symbol", "unknown")
        market = row.get("market", "unknown")
        time.sleep(sleep_seconds)
        _emit(
            {
                "type": "log",
                "level": "INFO",
                "message": f"Imported {symbol} from {market}.",
            }
        )
        _emit(
            {
                "type": "progress",
                "progress": round(index / total, 4),
                "message": f"Processed {index}/{total} rows.",
            }
        )

    _emit(
        {
            "type": "log",
            "level": "INFO",
            "message": "Sample data import completed.",
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
