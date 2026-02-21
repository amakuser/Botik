"""
Telegram-бот: /status, /pause, /resume, /panic, /set_risk.
Логирование всех команд. /panic по умолчанию только cancel all; market close только если allow_panic_market_close.
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from telebot import TeleBot
from telebot import types

if TYPE_CHECKING:
    from src.botik.config import AppConfig
    from src.botik.state.state import TradingState

logger = logging.getLogger(__name__)


def run_telegram_bot(
    token: str,
    state: "TradingState",
    config: "AppConfig",
    allowed_chat_id: str | None = None,
) -> None:
    """
    Запускает Telegram-бота в текущем потоке (вызывать из отдельного потока из main).
    Если allowed_chat_id задан — обрабатываем команды только из этого чата.
    """
    bot = TeleBot(token)

    def is_allowed(message) -> bool:
        if allowed_chat_id is None:
            return True
        return str(message.chat.id) == str(allowed_chat_id)

    @bot.message_handler(commands=["status"])
    def cmd_status(message):
        if not is_allowed(message):
            return
        logger.info("Telegram command: /status from chat_id=%s", message.chat.id)
        status = "приостановлена (paused)" if state.paused else "включена (running)"
        text = f"Торговля: {status}.\nСтаканы: {list(state.orderbooks.keys())}."
        bot.reply_to(message, text)

    @bot.message_handler(commands=["pause"])
    def cmd_pause(message):
        if not is_allowed(message):
            return
        logger.info("Telegram command: /pause from chat_id=%s", message.chat.id)
        state.set_paused(True)
        bot.reply_to(message, "Торговля приостановлена. Новые ордера не выставляются.")

    @bot.message_handler(commands=["resume"])
    def cmd_resume(message):
        if not is_allowed(message):
            return
        logger.info("Telegram command: /resume from chat_id=%s", message.chat.id)
        state.set_paused(False)
        bot.reply_to(message, "Торговля включена. Ордера разрешены.")

    @bot.message_handler(commands=["panic"])
    def cmd_panic(message):
        if not is_allowed(message):
            return
        logger.warning("Telegram command: /panic from chat_id=%s", message.chat.id)
        state.set_panic_requested(True)
        state.set_paused(True)
        if config.allow_panic_market_close:
            bot.reply_to(message, "PANIC: отмена всех ордеров и закрытие позиций (market).")
        else:
            bot.reply_to(message, "PANIC: отмена всех ордеров. Рыночное закрытие отключено в конфиге.")

    @bot.message_handler(commands=["set_risk"])
    def cmd_set_risk(message):
        if not is_allowed(message):
            return
        logger.info("Telegram command: /set_risk from chat_id=%s", message.chat.id)
        bot.reply_to(
            message,
            "Лимиты риска задаются в config.yaml (risk.*). Перезапустите бота после изменений.",
        )

    bot.infinity_polling()


def start_telegram_bot_in_thread(
    token: str,
    state: "TradingState",
    config: "AppConfig",
    allowed_chat_id: str | None = None,
) -> threading.Thread:
    """Запускает бота в фоновом потоке. Возвращает поток (daemon=True)."""
    t = threading.Thread(
        target=run_telegram_bot,
        args=(token, state, config),
        kwargs={"allowed_chat_id": allowed_chat_id},
        daemon=True,
    )
    t.start()
    return t


# --- Как проверить: передать токен и state, отправить /status, /pause, /resume в Telegram.
# --- Частые ошибки: не ограничить чат (allowed_chat_id) — любой может слать команды; забыть логировать команды.
# --- Что улучшить позже: /set_risk с аргументами (диапазон) и сохранение в runtime config.
