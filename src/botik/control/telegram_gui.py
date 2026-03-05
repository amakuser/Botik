"""
Telegram control bot for Desktop GUI supervisor process.

Works independently of trading subprocess lifecycle.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from telebot import TeleBot
from telebot import types

logger = logging.getLogger(__name__)

BTN_STATUS = "Статус"
BTN_BALANCE = "Средства"
BTN_ORDERS = "Ордера"
BTN_START = "Старт трейдинга"
BTN_STOP = "Стоп трейдинга"
BTN_PULL = "Обновить код"
BTN_RESTART_SOFT = "Рестарт мягко"
BTN_RESTART_HARD = "Рестарт жестко+обновить"
BTN_HELP = "Помощь"


class GuiTelegramActions:
    def __init__(
        self,
        status: Callable[[], str],
        balance: Callable[[], str],
        orders: Callable[[], str],
        start_trading: Callable[[], str],
        stop_trading: Callable[[], str],
        pull_updates: Callable[[], str],
        restart_soft: Callable[[], str],
        restart_hard: Callable[[], str],
    ) -> None:
        self.status = status
        self.balance = balance
        self.orders = orders
        self.start_trading = start_trading
        self.stop_trading = stop_trading
        self.pull_updates = pull_updates
        self.restart_soft = restart_soft
        self.restart_hard = restart_hard


def _main_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton(BTN_STATUS), types.KeyboardButton(BTN_BALANCE), types.KeyboardButton(BTN_ORDERS))
    kb.row(types.KeyboardButton(BTN_START), types.KeyboardButton(BTN_STOP))
    kb.row(types.KeyboardButton(BTN_PULL), types.KeyboardButton(BTN_RESTART_SOFT))
    kb.row(types.KeyboardButton(BTN_RESTART_HARD), types.KeyboardButton(BTN_HELP))
    return kb


def _help_text() -> str:
    return (
        "Команды:\n"
        "/status - статус GUI и процессов\n"
        "/balance - средства аккаунта\n"
        "/orders - активные ордера\n"
        "/starttrading - запустить трейдинг\n"
        "/stoptrading - остановить трейдинг\n"
        "/pull - git pull --ff-only\n"
        "/restartsoft - мягкий рестарт трейдинга\n"
        "/restarthard - жесткий рестарт с обновлением\n"
        "/help - подсказка"
    )


def run_gui_telegram_bot(
    token: str,
    actions: GuiTelegramActions,
    allowed_chat_id: str | None = None,
) -> None:
    bot = TeleBot(token)
    reply_kb = _main_keyboard()

    def is_allowed_chat(chat_id: int | str) -> bool:
        if allowed_chat_id is None:
            return True
        return str(chat_id) == str(allowed_chat_id)

    def is_allowed_message(message: types.Message) -> bool:
        return is_allowed_chat(message.chat.id)

    def send_text(chat_id: int, text: str) -> None:
        bot.send_message(chat_id, text, reply_markup=reply_kb)

    def run_async_action(chat_id: int, title: str, fn: Callable[[], str]) -> None:
        send_text(chat_id, f"{title}: выполняю...")

        def worker() -> None:
            try:
                result = fn()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Telegram GUI action failed: %s", title)
                result = f"{title}: ошибка: {exc}"
            send_text(chat_id, result)

        threading.Thread(target=worker, daemon=True).start()

    @bot.message_handler(commands=["start"])
    def cmd_start(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        logger.info("GUI Telegram command: /start from chat_id=%s", message.chat.id)
        send_text(message.chat.id, "GUI-контроль запущен.\n" + _help_text())

    @bot.message_handler(commands=["help"])
    def cmd_help(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        send_text(message.chat.id, _help_text())

    @bot.message_handler(commands=["status"])
    def cmd_status(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        send_text(message.chat.id, actions.status())

    @bot.message_handler(commands=["balance"])
    def cmd_balance(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        run_async_action(message.chat.id, "Средства", actions.balance)

    @bot.message_handler(commands=["orders"])
    def cmd_orders(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        run_async_action(message.chat.id, "Ордера", actions.orders)

    @bot.message_handler(commands=["starttrading"])
    def cmd_start_trading(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        run_async_action(message.chat.id, "Старт трейдинга", actions.start_trading)

    @bot.message_handler(commands=["stoptrading"])
    def cmd_stop_trading(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        run_async_action(message.chat.id, "Стоп трейдинга", actions.stop_trading)

    @bot.message_handler(commands=["pull"])
    def cmd_pull(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        run_async_action(message.chat.id, "Обновление кода", actions.pull_updates)

    @bot.message_handler(commands=["restartsoft"])
    def cmd_restart_soft(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        run_async_action(message.chat.id, "Мягкий рестарт", actions.restart_soft)

    @bot.message_handler(commands=["restarthard"])
    def cmd_restart_hard(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        run_async_action(message.chat.id, "Жесткий рестарт", actions.restart_hard)

    @bot.message_handler(func=lambda m: bool(m.text))
    def button_router(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        text = (message.text or "").strip()
        if text == BTN_STATUS:
            send_text(message.chat.id, actions.status())
        elif text == BTN_BALANCE:
            run_async_action(message.chat.id, "Средства", actions.balance)
        elif text == BTN_ORDERS:
            run_async_action(message.chat.id, "Ордера", actions.orders)
        elif text == BTN_START:
            run_async_action(message.chat.id, "Старт трейдинга", actions.start_trading)
        elif text == BTN_STOP:
            run_async_action(message.chat.id, "Стоп трейдинга", actions.stop_trading)
        elif text == BTN_PULL:
            run_async_action(message.chat.id, "Обновление кода", actions.pull_updates)
        elif text == BTN_RESTART_SOFT:
            run_async_action(message.chat.id, "Мягкий рестарт", actions.restart_soft)
        elif text == BTN_RESTART_HARD:
            run_async_action(message.chat.id, "Жесткий рестарт", actions.restart_hard)
        elif text == BTN_HELP:
            send_text(message.chat.id, _help_text())

    try:
        bot.set_my_commands(
            [
                types.BotCommand("start", "открыть GUI-контроль"),
                types.BotCommand("status", "статус процессов"),
                types.BotCommand("balance", "средства аккаунта"),
                types.BotCommand("orders", "активные ордера"),
                types.BotCommand("starttrading", "запустить трейдинг"),
                types.BotCommand("stoptrading", "остановить трейдинг"),
                types.BotCommand("pull", "подтянуть обновления"),
                types.BotCommand("restartsoft", "мягкий рестарт"),
                types.BotCommand("restarthard", "жесткий рестарт+обновить"),
                types.BotCommand("help", "список команд"),
            ]
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to set GUI Telegram commands: %s", exc)

    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
        except Exception as exc:  # noqa: BLE001
            logger.warning("GUI Telegram polling error, restart in 3s: %s", exc)
            time.sleep(3)


def start_gui_telegram_bot_in_thread(
    token: str,
    actions: GuiTelegramActions,
    allowed_chat_id: str | None = None,
) -> threading.Thread:
    t = threading.Thread(
        target=run_gui_telegram_bot,
        args=(token, actions),
        kwargs={"allowed_chat_id": allowed_chat_id},
        daemon=True,
    )
    t.start()
    return t

