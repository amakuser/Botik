"""
Настройка логирования с ротацией файлов.
Единый формат: время, уровень, логгер, сообщение.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logging(
    log_dir: str = "logs",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    level: int = logging.INFO,
) -> None:
    """
    Настраивает корневой логгер: консоль + ротируемый файл в log_dir.
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / "botik.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    # Консоль
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        root.addHandler(ch)

    # Файл с ротацией
    fh = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    fh.setFormatter(formatter)
    root.addHandler(fh)


# --- Как проверить: вызвать setup_logging(), затем logging.info("test") и проверить logs/botik.log
# --- Частые ошибки: вызвать setup_logging дважды — появятся дублирующие хендлеры (можно сбрасывать root.handlers перед настройкой).
# --- Что улучшить позже: отдельный уровень для файла и консоли; JSON-формат для парсинга.
