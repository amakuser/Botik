"""
Telegram control bot for runtime operations.

Commands:
- /start
- /help
- /status
- /scanner
- /pairs
- /pause
- /resume
- /panic
"""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from telebot import TeleBot
from telebot import types

if TYPE_CHECKING:
    from src.botik.config import AppConfig
    from src.botik.state.state import TradingState

logger = logging.getLogger(__name__)

BTN_STATUS = "Статус"
BTN_SCANNER = "Сканер"
BTN_PAIRS = "Пары"
BTN_PAUSE = "Пауза"
BTN_RESUME = "Продолжить"
BTN_PANIC = "Паника"
BTN_HELP = "Помощь"


def _main_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton(BTN_STATUS), types.KeyboardButton(BTN_SCANNER), types.KeyboardButton(BTN_PAIRS))
    kb.row(types.KeyboardButton(BTN_PAUSE), types.KeyboardButton(BTN_RESUME), types.KeyboardButton(BTN_PANIC))
    kb.row(types.KeyboardButton(BTN_HELP))
    return kb


def _controls_inline_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.row(
        types.InlineKeyboardButton("Статус", callback_data="ctl:status"),
        types.InlineKeyboardButton("Сканер", callback_data="ctl:scanner"),
        types.InlineKeyboardButton("Пары", callback_data="ctl:pairs"),
    )
    kb.row(
        types.InlineKeyboardButton("Пауза", callback_data="ctl:pause"),
        types.InlineKeyboardButton("Продолжить", callback_data="ctl:resume"),
        types.InlineKeyboardButton("Паника", callback_data="ctl:panic"),
    )
    return kb


def _runtime_status_text(state: "TradingState") -> str:
    run_state = "ПАУЗА" if state.paused else "РАБОТАЕТ"
    active_symbols = state.get_active_symbols()
    scanner = state.get_scanner_snapshot()
    return (
        f"Торговля: {run_state}\n"
        f"Флаг PANIC: {state.panic_requested}\n"
        f"Активные символы: {len(active_symbols)} ({', '.join(active_symbols[:8]) if active_symbols else 'нет'})\n"
        f"Сканер: pass={scanner.get('pass', 0)} watch={scanner.get('watch', 0)} "
        f"reject={scanner.get('reject', 0)} stale={scanner.get('stale', 0)} selected={scanner.get('selected', 0)}"
    )


def _scanner_text(state: "TradingState") -> str:
    s = state.get_scanner_snapshot()
    return (
        "Снимок сканера:\n"
        f"universe_total={s.get('universe_total', 0)}\n"
        f"pass={s.get('pass', 0)} watch={s.get('watch', 0)} reject={s.get('reject', 0)} stale={s.get('stale', 0)}\n"
        f"selected={s.get('selected', 0)} top_symbol={s.get('top_symbol', '')} "
        f"top_score_bps={float(s.get('top_score_bps', 0.0)):.4f}"
    )


def _pairs_text(state: "TradingState", limit: int = 10) -> str:
    snapshots = state.get_all_pair_filter_snapshots()
    if not snapshots:
        return "Снимки pair-фильтра пока не готовы."

    status_rank = {"PASS": 0, "WATCH": 1, "REJECT": 2}
    rows = sorted(
        snapshots.items(),
        key=lambda kv: (
            status_rank.get(str(kv[1].get("status", "REJECT")).upper(), 3),
            -float(kv[1].get("median_spread_bps", 0.0)),
        ),
    )
    lines: list[str] = []
    for symbol, snap in rows[: max(limit, 1)]:
        lines.append(
            f"{symbol}: {snap.get('status', 'NA')} {snap.get('reason', 'NA')} | "
            f"spread={float(snap.get('median_spread_bps', 0.0)):.2f}bps "
            f"req={float(snap.get('min_required_spread_bps', 0.0)):.2f}bps "
            f"trades/min={float(snap.get('trades_per_min', 0.0)):.1f} "
            f"stale={bool(snap.get('stale_data', True))}"
        )
    return "Фильтр пар (топ):\n" + "\n".join(lines)


def _help_text() -> str:
    return (
        "Команды:\n"
        "/status - текущий статус\n"
        "/scanner - сводка сканера\n"
        "/pairs - статусы пар\n"
        "/pause - поставить торговлю на паузу\n"
        "/resume - продолжить торговлю\n"
        "/panic - аварийная остановка (cancel-all)\n"
        "/help - подсказка"
    )


def run_telegram_bot(
    token: str,
    state: "TradingState",
    config: "AppConfig",
    allowed_chat_id: str | None = None,
) -> None:
    """
    Run Telegram bot in the current thread.
    If allowed_chat_id is set, only that chat can control the bot.
    """
    bot = TeleBot(token)
    reply_kb = _main_keyboard()
    inline_kb = _controls_inline_keyboard()

    def is_allowed_chat(chat_id: int | str) -> bool:
        if allowed_chat_id is None:
            return True
        return str(chat_id) == str(allowed_chat_id)

    def is_allowed_message(message: types.Message) -> bool:
        return is_allowed_chat(message.chat.id)

    def send_text(chat_id: int, text: str, with_inline: bool = False) -> None:
        kwargs: dict[str, object] = {"reply_markup": reply_kb}
        if with_inline:
            kwargs["reply_markup"] = inline_kb
        bot.send_message(chat_id, text, **kwargs)

    def do_pause(chat_id: int) -> None:
        state.set_paused(True)
        send_text(chat_id, "Торговля поставлена на паузу. Новые ордера отключены.")

    def do_resume(chat_id: int) -> None:
        state.set_paused(False)
        send_text(chat_id, "Торговля продолжена. Новые ордера разрешены.")

    def do_panic(chat_id: int) -> None:
        state.set_panic_requested(True)
        state.set_paused(True)
        if config.allow_panic_market_close:
            send_text(chat_id, "PANIC установлен: cancel-all + market close разрешен в config.")
        else:
            send_text(chat_id, "PANIC установлен: запрошен cancel-all. Market close отключен в config.")

    @bot.message_handler(commands=["start"])
    def cmd_start(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        logger.info("Telegram command: /start from chat_id=%s", message.chat.id)
        bot.reply_to(
            message,
            "Botik control запущен.\n" + _help_text(),
            reply_markup=reply_kb,
        )
        bot.send_message(message.chat.id, "Быстрые кнопки:", reply_markup=inline_kb)

    @bot.message_handler(commands=["help"])
    def cmd_help(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        logger.info("Telegram command: /help from chat_id=%s", message.chat.id)
        bot.reply_to(message, _help_text(), reply_markup=reply_kb)

    @bot.message_handler(commands=["status"])
    def cmd_status(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        logger.info("Telegram command: /status from chat_id=%s", message.chat.id)
        bot.reply_to(message, _runtime_status_text(state), reply_markup=reply_kb)

    @bot.message_handler(commands=["scanner"])
    def cmd_scanner(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        logger.info("Telegram command: /scanner from chat_id=%s", message.chat.id)
        bot.reply_to(message, _scanner_text(state), reply_markup=reply_kb)

    @bot.message_handler(commands=["pairs"])
    def cmd_pairs(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        logger.info("Telegram command: /pairs from chat_id=%s", message.chat.id)
        bot.reply_to(message, _pairs_text(state), reply_markup=reply_kb)

    @bot.message_handler(commands=["pause"])
    def cmd_pause(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        logger.info("Telegram command: /pause from chat_id=%s", message.chat.id)
        do_pause(message.chat.id)

    @bot.message_handler(commands=["resume"])
    def cmd_resume(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        logger.info("Telegram command: /resume from chat_id=%s", message.chat.id)
        do_resume(message.chat.id)

    @bot.message_handler(commands=["panic"])
    def cmd_panic(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        logger.warning("Telegram command: /panic from chat_id=%s", message.chat.id)
        do_panic(message.chat.id)

    @bot.message_handler(func=lambda m: bool(m.text))
    def button_router(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        text = (message.text or "").strip()
        if text == BTN_STATUS:
            bot.reply_to(message, _runtime_status_text(state), reply_markup=reply_kb)
        elif text == BTN_SCANNER:
            bot.reply_to(message, _scanner_text(state), reply_markup=reply_kb)
        elif text == BTN_PAIRS:
            bot.reply_to(message, _pairs_text(state), reply_markup=reply_kb)
        elif text == BTN_PAUSE:
            do_pause(message.chat.id)
        elif text == BTN_RESUME:
            do_resume(message.chat.id)
        elif text == BTN_PANIC:
            do_panic(message.chat.id)
        elif text == BTN_HELP:
            bot.reply_to(message, _help_text(), reply_markup=reply_kb)

    @bot.callback_query_handler(func=lambda call: str(call.data).startswith("ctl:"))
    def callback_controls(call: types.CallbackQuery) -> None:
        chat_id = call.message.chat.id if call.message else 0
        if not is_allowed_chat(chat_id):
            bot.answer_callback_query(call.id, "Доступ запрещен")
            return

        action = str(call.data).split(":", 1)[1]
        logger.info("Telegram callback: %s from chat_id=%s", action, chat_id)
        if action == "status":
            bot.send_message(chat_id, _runtime_status_text(state), reply_markup=reply_kb)
        elif action == "scanner":
            bot.send_message(chat_id, _scanner_text(state), reply_markup=reply_kb)
        elif action == "pairs":
            bot.send_message(chat_id, _pairs_text(state), reply_markup=reply_kb)
        elif action == "pause":
            do_pause(chat_id)
        elif action == "resume":
            do_resume(chat_id)
        elif action == "panic":
            do_panic(chat_id)
        bot.answer_callback_query(call.id)

    try:
        bot.set_my_commands(
            [
                types.BotCommand("start", "открыть управление"),
                types.BotCommand("help", "список команд"),
                types.BotCommand("status", "текущий статус"),
                types.BotCommand("scanner", "сводка сканера"),
                types.BotCommand("pairs", "статусы пар"),
                types.BotCommand("pause", "пауза торговли"),
                types.BotCommand("resume", "продолжить торговлю"),
                types.BotCommand("panic", "аварийная остановка"),
            ]
        )
    except Exception as exc:
        logger.warning("Failed to set Telegram bot commands: %s", exc)

    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
        except Exception as exc:
            logger.warning("Telegram polling error, restart in 3s: %s", exc)
            time.sleep(3)


def start_telegram_bot_in_thread(
    token: str,
    state: "TradingState",
    config: "AppConfig",
    allowed_chat_id: str | None = None,
) -> threading.Thread:
    """Start Telegram bot in a daemon thread and return it."""
    t = threading.Thread(
        target=run_telegram_bot,
        args=(token, state, config),
        kwargs={"allowed_chat_id": allowed_chat_id},
        daemon=True,
    )
    t.start()
    return t
