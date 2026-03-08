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
- /update
"""
from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from telebot import TeleBot
from telebot import types

if TYPE_CHECKING:
    from src.botik.config import AppConfig
    from src.botik.state.state import TradingState

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[3]
VERSION_FILE = ROOT_DIR / "version.txt"

BTN_STATUS = "Статус"
BTN_SCANNER = "Сканер"
BTN_PAIRS = "Пары"
BTN_PAUSE = "Пауза"
BTN_RESUME = "Продолжить"
BTN_PANIC = "Паника"
BTN_HELP = "Помощь"
BTN_UPDATE = "Update"


def _main_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton(BTN_STATUS), types.KeyboardButton(BTN_SCANNER), types.KeyboardButton(BTN_PAIRS))
    kb.row(types.KeyboardButton(BTN_PAUSE), types.KeyboardButton(BTN_RESUME), types.KeyboardButton(BTN_PANIC))
    kb.row(types.KeyboardButton(BTN_HELP), types.KeyboardButton(BTN_UPDATE))
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
    kb.row(types.InlineKeyboardButton("Update", callback_data="ctl:update"))
    return kb


def _run_git(args: list[str], repo_root: Path) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return proc.returncode, output


def _read_version_file(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write_version_file(path: Path, version: str) -> None:
    path.write_text((version or "").strip() + "\n", encoding="utf-8")


def _git_head(repo_root: Path) -> str:
    code, out = _run_git(["rev-parse", "HEAD"], repo_root)
    if code != 0:
        return ""
    return out.splitlines()[0].strip()


def _git_remote_head(repo_root: Path) -> str:
    for branch in ("master", "main"):
        code, out = _run_git(["ls-remote", "--heads", "origin", branch], repo_root)
        if code != 0:
            continue
        line = out.splitlines()[0].strip() if out.splitlines() else ""
        if not line:
            continue
        parts = line.split()
        if parts:
            return parts[0].strip()
    return ""


def _resolve_local_version(repo_root: Path, version_file: Path) -> str:
    git_version = _git_head(repo_root)
    if git_version:
        return git_version
    return _read_version_file(version_file)


def perform_update(repo_root: Path, version_file: Path) -> tuple[str, str]:
    """
    Returns:
    - ("up_to_date", version)
    - ("updated", new_version)
    - ("dirty_tree", status_output)
    - ("remote_unavailable", "")
    - ("pull_failed", stderr_or_output)
    """
    current_version = _resolve_local_version(repo_root, version_file)
    code, worktree = _run_git(["status", "--porcelain"], repo_root)
    if code != 0:
        return "pull_failed", worktree
    if (worktree or "").strip():
        return "dirty_tree", worktree
    remote_version = _git_remote_head(repo_root)
    if not remote_version:
        return "remote_unavailable", ""
    if remote_version == current_version:
        if current_version:
            _write_version_file(version_file, current_version)
        return "up_to_date", current_version

    logger.info("Pulling latest code...")
    code, out = _run_git(["pull", "--ff-only"], repo_root)
    if code != 0:
        return "pull_failed", out
    new_version = _git_head(repo_root) or _resolve_local_version(repo_root, version_file)
    if new_version:
        _write_version_file(version_file, new_version)
    return "updated", new_version


def _runtime_status_text(state: "TradingState") -> str:
    run_state = "ПАУЗА" if state.paused else "РАБОТАЕТ"
    active_symbols = state.get_active_symbols()
    scanner = state.get_scanner_snapshot()
    version = state.get_current_version() or _read_version_file(VERSION_FILE) or "unknown"
    upd_state = "IN_PROGRESS" if state.update_in_progress else "IDLE"
    upd_msg = state.get_update_message() or "-"
    return (
        f"Торговля: {run_state}\n"
        f"Флаг PANIC: {state.panic_requested}\n"
        f"Версия: {version[:12]}\n"
        f"Update: {upd_state} ({upd_msg})\n"
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
        "/update - подтянуть обновления из GitHub и мягко перезапустить торговый цикл\n"
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
    update_lock = threading.Lock()
    state.set_current_version(_resolve_local_version(ROOT_DIR, VERSION_FILE))

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

    def _update_worker(chat_id: int) -> None:
        logger.info("Update command received")
        with update_lock:
            if state.update_in_progress:
                logger.warning("Update already in progress")
                send_text(chat_id, "Обновление уже выполняется")
                return
            state.set_update_in_progress(True, "checking")
        try:
            current_version = _resolve_local_version(ROOT_DIR, VERSION_FILE)
            state.set_current_version(current_version)
            status, payload = perform_update(ROOT_DIR, VERSION_FILE)
            if status == "remote_unavailable":
                state.set_update_in_progress(False, "remote_unavailable")
                send_text(chat_id, "Не удалось получить версию из GitHub.")
                return

            if status == "dirty_tree":
                state.set_update_in_progress(False, "dirty_tree")
                send_text(
                    chat_id,
                    "Обновление остановлено: в рабочем дереве есть локальные изменения.\n"
                    "Сначала закоммитьте или спрячьте их (stash), затем повторите /update.",
                )
                return

            if status == "up_to_date":
                state.set_update_in_progress(False, "up_to_date")
                send_text(chat_id, f"Обновление не требуется. Текущая версия: {current_version[:12]}")
                return

            if status == "pull_failed":
                state.set_update_in_progress(False, "pull_failed")
                send_text(chat_id, f"Ошибка git pull:\n{payload[-3500:]}")
                return

            new_version = payload
            if new_version:
                state.set_current_version(new_version)
            logger.info("Update applied, new version: %s", new_version)

            # Keep Telegram bot online; request soft restart of trading runtime in main loop.
            state.set_restart_requested(True)
            state.set_update_in_progress(True, f"restart_pending:{new_version[:12] if new_version else 'unknown'}")
            send_text(chat_id, f"Обновление выполнено. Текущая версия: {new_version[:12]}.")
        except Exception as exc:
            state.set_update_in_progress(False, "error")
            send_text(chat_id, f"Ошибка обновления: {exc}")

    def do_update(chat_id: int) -> None:
        if state.update_in_progress:
            logger.warning("Update already in progress")
            send_text(chat_id, "Обновление уже выполняется")
            return
        send_text(chat_id, "Проверяю обновления...")
        threading.Thread(target=_update_worker, args=(chat_id,), daemon=True).start()

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
        current_version = _resolve_local_version(ROOT_DIR, VERSION_FILE)
        if current_version:
            state.set_current_version(current_version)
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

    @bot.message_handler(commands=["update"])
    def cmd_update(message: types.Message) -> None:
        if not is_allowed_message(message):
            return
        do_update(message.chat.id)

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
        elif text == BTN_UPDATE:
            do_update(message.chat.id)
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
        elif action == "update":
            do_update(chat_id)
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
                types.BotCommand("update", "обновить код и мягко перезапустить цикл"),
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
