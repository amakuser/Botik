"""
notifier.py — Отправка push-алертов в Telegram.

Простой fire-and-forget модуль без внешних зависимостей.
Читает TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID из .env или os.environ.
Ошибки логируются, но не прерывают основной поток.

Использование:
    from src.botik.control.notifier import send_alert
    send_alert("🟢 ОТКРЫТА: BTCUSDT Long | Вход $65,432")
"""
from __future__ import annotations

import json
import logging
import os
import threading
import urllib.request
from pathlib import Path

log = logging.getLogger("botik.notifier")

# Путь к .env (ищем от корня проекта вверх)
def _find_env_path() -> Path | None:
    here = Path(__file__).resolve()
    for parent in [here.parent, here.parent.parent, here.parent.parent.parent,
                   here.parent.parent.parent.parent]:
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
    return None


def _read_env() -> tuple[str, str]:
    """Возвращает (token, chat_id) из .env или os.environ."""
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    env_path = _find_env_path()
    if env_path:
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if "=" not in line or line.startswith("#"):
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if k == "TELEGRAM_BOT_TOKEN" and not token:
                    token = v
                elif k == "TELEGRAM_CHAT_ID" and not chat_id:
                    chat_id = v
        except Exception:
            pass

    return token, chat_id


def _do_send(text: str) -> None:
    """Фактическая отправка через Telegram Bot API (вызывается в отдельном потоке)."""
    token, chat_id = _read_env()
    if not token or not chat_id:
        log.debug("notifier: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID не заданы — алерт пропущен")
        return
    try:
        url     = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req     = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read())
            if not body.get("ok"):
                log.warning("notifier: Telegram error: %s", body)
    except Exception as exc:
        log.warning("notifier: send failed: %s", exc)


def send_alert(text: str) -> None:
    """
    Отправить сообщение в Telegram асинхронно (fire-and-forget).
    Никогда не бросает исключений — ошибки логируются в debug/warning.
    """
    t = threading.Thread(target=_do_send, args=(text,), daemon=True)
    t.start()
