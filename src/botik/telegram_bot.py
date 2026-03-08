"""
Compatibility entrypoint for running Telegram control bot directly.
"""
from __future__ import annotations

import logging

from src.botik.config import load_config
from src.botik.control.telegram_bot import run_telegram_bot
from src.botik.state.state import TradingState
from src.botik.utils.logging import setup_logging


def main() -> None:
    config = load_config()
    setup_logging(
        log_dir=config.logging.dir,
        max_bytes=config.logging.max_bytes,
        backup_count=config.logging.backup_count,
    )
    token = config.get_telegram_token()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set.")
    state = TradingState()
    state.set_paused(config.start_paused)
    run_telegram_bot(
        token=token,
        state=state,
        config=config,
        allowed_chat_id=config.get_telegram_chat_id(),
    )


if __name__ == "__main__":
    logging.getLogger(__name__).setLevel(logging.INFO)
    main()
