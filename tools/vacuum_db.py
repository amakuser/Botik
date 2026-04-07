"""
vacuum_db.py — Восстановление пространства SQLite после миграций.

Запускать ОФЛАЙН когда Botik не работает.
После удаления колонок (migration 14) или удаления данных SQLite не
возвращает место на диск автоматически.  VACUUM перестраивает базу
и реально уменьшает файл.

Для price_history после migration 14 (~27M строк, -25 байт/строка):
  ожидаемая экономия ≈ 675 MB

Использование:
  python tools/vacuum_db.py [--db PATH_TO_DB]
"""
import argparse
import sys
import time
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from src.botik.storage.db import get_db
    _HAS_GET_DB = True
except ImportError:
    _HAS_GET_DB = False


def _find_db() -> Path | None:
    """Ищет botik.db в стандартных местах."""
    candidates = [
        Path("data/botik.db"),
        Path("botik.db"),
        Path.home() / "botik" / "data" / "botik.db",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def vacuum(db_path: Path) -> None:
    import sqlite3

    size_before = db_path.stat().st_size
    print(f"Database : {db_path}")
    print(f"Size before: {size_before / 1_048_576:.1f} MB")

    print("Running VACUUM … (this may take several minutes for large databases)")
    t0 = time.monotonic()
    conn = sqlite3.connect(str(db_path), timeout=300)
    try:
        conn.execute("VACUUM")
        conn.close()
    except Exception as exc:
        conn.close()
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.monotonic() - t0
    size_after = db_path.stat().st_size
    saved = size_before - size_after

    print(f"Done in {elapsed:.1f}s")
    print(f"Size after : {size_after / 1_048_576:.1f} MB")
    print(f"Saved      : {saved / 1_048_576:.1f} MB "
          f"({100 * saved / size_before:.1f}%)" if size_before else "n/a")


def main() -> None:
    parser = argparse.ArgumentParser(description="Vacuum Botik SQLite database")
    parser.add_argument("--db", metavar="PATH", help="Path to botik.db")
    args = parser.parse_args()

    if args.db:
        db_path = Path(args.db)
    else:
        db_path = _find_db()

    if db_path is None or not db_path.exists():
        print("ERROR: database file not found.  Use --db PATH", file=sys.stderr)
        sys.exit(1)

    vacuum(db_path)


if __name__ == "__main__":
    main()
