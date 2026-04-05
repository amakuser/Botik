"""
Preflight — комплексная проверка системы перед стартом / после обновления.

Уровни:
  REQUIRED  — если провалилась, завершаем с exit code 2 (критические)
  IMPORTANT — предупреждение, exit code 1 (нужны для торговли)
  INFO      — информационная, не влияет на exit code

Запуск:
  python tools/preflight.py
  python tools/preflight.py --json
  python tools/preflight.py --skip-api --skip-ws
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env", override=False)
except ImportError:
    pass

# ── Цвета для терминала ────────────────────────────────────────────────────

_NO_COLOR = os.environ.get("NO_COLOR") or not sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    if _NO_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

_GREEN  = lambda t: _c("32", t)
_YELLOW = lambda t: _c("33", t)
_RED    = lambda t: _c("31", t)
_CYAN   = lambda t: _c("36", t)
_BOLD   = lambda t: _c("1",  t)
_DIM    = lambda t: _c("2",  t)


# ── Результат проверки ─────────────────────────────────────────────────────

class CheckResult:
    def __init__(
        self,
        name: str,
        level: str,           # REQUIRED | IMPORTANT | INFO
        ok: bool,
        message: str,
        detail: dict | None = None,
    ) -> None:
        self.name    = name
        self.level   = level
        self.ok      = ok
        self.message = message
        self.detail  = detail or {}

    def to_dict(self) -> dict:
        return {
            "name":    self.name,
            "level":   self.level,
            "ok":      self.ok,
            "message": self.message,
            "detail":  self.detail,
        }

    def print_line(self) -> None:
        icon = _GREEN("OK") if self.ok else (_YELLOW("!!") if self.level != "REQUIRED" else _RED("XX"))
        level_str = _DIM(f"[{self.level}]".ljust(12))
        name_str  = self.name.ljust(30)
        msg       = self.message
        if not self.ok and self.level == "REQUIRED":
            msg = _RED(msg)
        elif not self.ok:
            msg = _YELLOW(msg)
        else:
            msg = _GREEN(msg)
        print(f"  {icon} {level_str} {name_str} {msg}")


# ── 1. DATABASE ────────────────────────────────────────────────────────────

def check_db() -> CheckResult:
    """DB: подключение и применение миграций."""
    try:
        from src.botik.storage.schema import bootstrap_db
        db = bootstrap_db()
        with db.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
        return CheckResult(
            "db:connect",
            "REQUIRED",
            ok=True,
            message=f"OK — {count} таблиц",
            detail={"tables": count},
        )
    except Exception as exc:
        return CheckResult(
            "db:connect",
            "REQUIRED",
            ok=False,
            message=f"Ошибка: {exc}",
        )


def check_db_tables() -> CheckResult:
    """DB: ключевые таблицы существуют."""
    required_tables = [
        "price_history",
        "futures_paper_trades",
        "spot_holdings",
        "labeled_samples",
        "ml_training_runs",
        "app_logs",
    ]
    try:
        from src.botik.storage.db import get_db
        db = get_db()
        with db.connect() as conn:
            existing = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        missing = [t for t in required_tables if t not in existing]
        if missing:
            return CheckResult(
                "db:tables",
                "REQUIRED",
                ok=False,
                message=f"Не найдены таблицы: {', '.join(missing)}",
                detail={"missing": missing},
            )
        return CheckResult(
            "db:tables",
            "REQUIRED",
            ok=True,
            message=f"OK — все {len(required_tables)} таблиц на месте",
        )
    except Exception as exc:
        return CheckResult(
            "db:tables",
            "REQUIRED",
            ok=False,
            message=f"Ошибка: {exc}",
        )


# ── 2. CONFIG / ENV ────────────────────────────────────────────────────────

def check_env_api_keys() -> CheckResult:
    """ENV: BYBIT_API_KEY и BYBIT_API_SECRET_KEY заданы."""
    api_key    = os.environ.get("BYBIT_API_KEY", "").strip()
    api_secret = os.environ.get("BYBIT_API_SECRET_KEY", "").strip()
    if not api_key and not api_secret:
        return CheckResult(
            "env:bybit_keys",
            "IMPORTANT",
            ok=False,
            message="Не заданы BYBIT_API_KEY / BYBIT_API_SECRET_KEY — только demo/paper режим",
        )
    if not api_key or not api_secret:
        missing = "BYBIT_API_KEY" if not api_key else "BYBIT_API_SECRET_KEY"
        return CheckResult(
            "env:bybit_keys",
            "IMPORTANT",
            ok=False,
            message=f"Не задан {missing}",
        )
    return CheckResult(
        "env:bybit_keys",
        "IMPORTANT",
        ok=True,
        message=f"OK — ключ {'*' * 6}{api_key[-4:]}",
        detail={"key_suffix": api_key[-4:]},
    )


def check_env_telegram() -> CheckResult:
    """ENV: TELEGRAM_BOT_TOKEN задан."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return CheckResult(
            "env:telegram",
            "IMPORTANT",
            ok=False,
            message="TELEGRAM_BOT_TOKEN не задан — уведомления отключены",
        )
    return CheckResult(
        "env:telegram",
        "IMPORTANT",
        ok=True,
        message=f"OK — токен {'*' * 6}{token[-4:]}",
    )


def check_env_host() -> CheckResult:
    """ENV: BYBIT_HOST задан (необязательно)."""
    host = os.environ.get("BYBIT_HOST", "api-demo.bybit.com").strip()
    return CheckResult(
        "env:bybit_host",
        "INFO",
        ok=True,
        message=f"host={host}",
        detail={"host": host},
    )


# ── 3. DATA ────────────────────────────────────────────────────────────────

def check_price_history() -> CheckResult:
    """DATA: свечи в price_history."""
    MIN_CANDLES = 500
    try:
        from src.botik.storage.db import get_db
        db = get_db()
        with db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM price_history"
            ).fetchone()
        count = row[0] if row else 0
        if count < MIN_CANDLES:
            return CheckResult(
                "data:price_history",
                "IMPORTANT",
                ok=False,
                message=(
                    f"Только {count} свечей (нужно ≥{MIN_CANDLES}) — "
                    "запустите: python -m src.botik.runners.data_runner --once"
                ),
                detail={"candles": count},
            )
        return CheckResult(
            "data:price_history",
            "IMPORTANT",
            ok=True,
            message=f"OK — {count:,} свечей",
            detail={"candles": count},
        )
    except Exception as exc:
        return CheckResult(
            "data:price_history",
            "IMPORTANT",
            ok=False,
            message=f"Ошибка: {exc}",
        )


# ── 4. ML ──────────────────────────────────────────────────────────────────

def check_ml_models() -> list[CheckResult]:
    """ML: модели обучены и файлы существуют."""
    results: list[CheckResult] = []
    try:
        from src.botik.ml.registry import MODELS_DIR as models_dir
    except Exception:
        models_dir = _ROOT / "data" / "models"

    for scope in ("futures", "spot"):
        for mname in ("historian", "predictor"):
            files = sorted(models_dir.glob(f"{scope}_{mname}_v*.joblib"))
            if not files:
                results.append(CheckResult(
                    f"ml:{scope}_{mname}",
                    "INFO",
                    ok=False,
                    message=(
                        "Модель не обучена — "
                        "запустите data_runner для bootstrap"
                    ),
                ))
                continue

            latest = files[-1]
            # Читаем точность из файла
            accuracy_str = ""
            try:
                import joblib
                payload = joblib.load(latest)
                acc = float(payload.get("accuracy", 0.0))
                accuracy_str = f" acc={acc:.3f}"
            except Exception:
                pass

            results.append(CheckResult(
                f"ml:{scope}_{mname}",
                "INFO",
                ok=True,
                message=f"OK — {latest.name}{accuracy_str}",
                detail={"file": str(latest), "version": latest.stem.split("_v")[-1]},
            ))

    # ML training runs summary из БД
    try:
        from src.botik.storage.db import get_db
        db = get_db()
        with db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM ml_training_runs WHERE is_trained=1"
            ).fetchone()
        trained = row[0] if row else 0
        results.append(CheckResult(
            "ml:training_runs",
            "INFO",
            ok=True,
            message=f"{trained} обученных запусков в БД",
            detail={"trained_runs": trained},
        ))
    except Exception:
        pass

    return results


# ── 5. API / WS (async) ────────────────────────────────────────────────────

def _sanitize_category(category: str) -> str:
    value = str(category or "").strip().lower()
    return value if value in {"spot", "linear"} else "spot"


async def _check_rest_public(host: str, timeout: float) -> CheckResult:
    try:
        import aiohttp
        url = f"https://{host}/v5/market/time"
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                data = await resp.json()
        if data.get("retCode") != 0:
            raise RuntimeError(f"retCode={data.get('retCode')}")
        return CheckResult(
            "api:rest_public",
            "INFO",
            ok=True,
            message=f"OK — {host}",
        )
    except Exception as exc:
        return CheckResult(
            "api:rest_public",
            "INFO",
            ok=False,
            message=f"Недоступен {host}: {exc}",
        )


async def _check_ws(host: str, symbol: str, category: str, timeout: float) -> CheckResult:
    try:
        import websockets
        cat = _sanitize_category(category)
        url = f"wss://{host}/v5/public/{cat}"
        topic = f"orderbook.1.{symbol}"
        async with websockets.connect(
            url, ping_interval=20, ping_timeout=10, close_timeout=5,
            open_timeout=timeout,
        ) as ws:
            await ws.send(json.dumps({"op": "subscribe", "args": [topic]}))
            for _ in range(3):
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                msg = json.loads(raw)
                if msg.get("topic") == topic:
                    bids = (msg.get("data") or {}).get("b", [])
                    asks = (msg.get("data") or {}).get("a", [])
                    if bids and asks:
                        bid = float(bids[0][0])
                        ask = float(asks[0][0])
                        return CheckResult(
                            "api:ws",
                            "INFO",
                            ok=True,
                            message=f"OK — {symbol} bid={bid} ask={ask}",
                            detail={"bid": bid, "ask": ask},
                        )
        return CheckResult("api:ws", "INFO", ok=False, message="Нет данных orderbook")
    except Exception as exc:
        return CheckResult(
            "api:ws",
            "INFO",
            ok=False,
            message=f"WS недоступен: {exc}",
        )


async def _check_rest_auth(host: str, symbol: str, category: str, timeout: float) -> CheckResult:
    api_key    = os.environ.get("BYBIT_API_KEY", "").strip()
    api_secret = os.environ.get("BYBIT_API_SECRET_KEY", "").strip()
    if not api_key or not api_secret:
        return CheckResult(
            "api:rest_auth",
            "INFO",
            ok=False,
            message="Пропущено — ключи не заданы",
            detail={"skipped": True},
        )
    try:
        from src.botik.execution.bybit_rest import BybitRestClient
        client = BybitRestClient(
            base_url=f"https://{host}",
            api_key=api_key,
            api_secret=api_secret,
            category=_sanitize_category(category),
        )
        out = await client.get_open_orders(symbol=symbol)
        if out.get("retCode") != 0:
            raise RuntimeError(f"retCode={out.get('retCode')} {out.get('retMsg')}")
        return CheckResult(
            "api:rest_auth",
            "IMPORTANT",
            ok=True,
            message="OK — аутентификация прошла",
        )
    except Exception as exc:
        return CheckResult(
            "api:rest_auth",
            "IMPORTANT",
            ok=False,
            message=f"Auth failed: {exc}",
        )


async def _check_telegram(timeout: float) -> CheckResult:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return CheckResult(
            "telegram:bot",
            "INFO",
            ok=False,
            message="Пропущено — токен не задан",
            detail={"skipped": True},
        )
    try:
        import aiohttp
        url = f"https://api.telegram.org/bot{token}/getMe"
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                data = await resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API: {data.get('description')}")
        username = data.get("result", {}).get("username", "?")
        return CheckResult(
            "telegram:bot",
            "IMPORTANT",
            ok=True,
            message=f"OK — @{username}",
            detail={"username": username},
        )
    except Exception as exc:
        return CheckResult(
            "telegram:bot",
            "IMPORTANT",
            ok=False,
            message=f"Ошибка: {exc}",
        )


# ── Runner ────────────────────────────────────────────────────────────────

async def _run_async(args: argparse.Namespace) -> int:
    host     = os.environ.get("BYBIT_HOST", "api-demo.bybit.com").strip()
    symbol   = args.symbol or "BTCUSDT"
    category = args.category or "linear"
    timeout  = args.timeout

    all_checks: list[CheckResult] = []

    # ── REQUIRED ──────────────────────────────
    print(_BOLD("\n-- DATABASE --------------------------------"))
    r_db       = check_db()
    r_dbtables = check_db_tables()
    all_checks += [r_db, r_dbtables]
    r_db.print_line()
    r_dbtables.print_line()

    # ── IMPORTANT ─────────────────────────────
    print(_BOLD("\n-- CONFIG / ENV ----------------------------"))
    r_keys = check_env_api_keys()
    r_tg   = check_env_telegram()
    r_host = check_env_host()
    all_checks += [r_keys, r_tg, r_host]
    r_keys.print_line()
    r_tg.print_line()
    r_host.print_line()

    print(_BOLD("\n-- DATA ------------------------------------"))
    r_hist = check_price_history()
    all_checks.append(r_hist)
    r_hist.print_line()

    # ── INFO ───────────────────────────────────
    print(_BOLD("\n-- ML MODELS ------------------------------"))
    ml_checks = check_ml_models()
    all_checks += ml_checks
    for r in ml_checks:
        r.print_line()

    if not args.skip_api:
        print(_BOLD("\n-- BYBIT API ------------------------------"))
        r_rest = await _check_rest_public(host, timeout)
        all_checks.append(r_rest)
        r_rest.print_line()

        if not args.skip_ws:
            r_ws = await _check_ws(host, symbol, category, timeout)
            all_checks.append(r_ws)
            r_ws.print_line()

        r_auth = await _check_rest_auth(host, symbol, category, timeout)
        all_checks.append(r_auth)
        r_auth.print_line()

    print(_BOLD("\n-- TELEGRAM --------------------------------"))
    r_tgbot = await _check_telegram(timeout)
    all_checks.append(r_tgbot)
    r_tgbot.print_line()

    # ── Итог ──────────────────────────────────
    required_failed  = [c for c in all_checks if c.level == "REQUIRED"  and not c.ok]
    important_failed = [c for c in all_checks if c.level == "IMPORTANT" and not c.ok]
    total_ok         = sum(1 for c in all_checks if c.ok)

    print()
    print("-" * 52)
    print(f"  Всего проверок : {len(all_checks)}")
    print(f"  Прошло         : {_GREEN(str(total_ok))}")
    if required_failed:
        print(f"  Критических    : {_RED(str(len(required_failed)))}")
    if important_failed:
        print(f"  Предупреждений : {_YELLOW(str(len(important_failed)))}")
    print("-" * 52)

    if required_failed:
        print(_RED("\n  PREFLIGHT FAILED — критические проверки не прошли:"))
        for c in required_failed:
            print(f"    • {c.name}: {c.message}")
        exit_code = 2
    elif important_failed:
        print(_YELLOW("\n  PREFLIGHT WARN — важные проверки не прошли:"))
        for c in important_failed:
            print(f"    • {c.name}: {c.message}")
        exit_code = 1
    else:
        print(_GREEN("\n  PREFLIGHT OK"))
        exit_code = 0

    print()

    if args.json:
        output = {
            "exit_code": exit_code,
            "host": host,
            "checks": [c.to_dict() for c in all_checks],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="Botik preflight — комплексная проверка системы")
    parser.add_argument("--symbol",   default="BTCUSDT",  help="Символ для API/WS проверок")
    parser.add_argument("--category", default="linear",   help="spot | linear")
    parser.add_argument("--timeout",  type=float, default=10.0, help="Таймаут для сетевых проверок (сек)")
    parser.add_argument("--skip-api", action="store_true", help="Пропустить REST/WS проверки Bybit")
    parser.add_argument("--skip-ws",  action="store_true", help="Пропустить WS проверку")
    parser.add_argument("--json",     action="store_true", help="Вывести JSON в конце")
    args = parser.parse_args()
    code = asyncio.run(_run_async(args))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
