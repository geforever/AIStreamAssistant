"""日志:rich 彩色 + rotating file。"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

_LEVELS = {
    "debug":   logging.DEBUG,
    "info":    logging.INFO,
    "warning": logging.WARNING,
    "error":   logging.ERROR,
}


def setup_logging(level: str, file: str) -> None:
    Path(file).parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RichHandler(rich_tracebacks=True, show_path=False),
        RotatingFileHandler(file, maxBytes=10_000_000, backupCount=5, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=_LEVELS[level],
        format="%(message)s",
        datefmt="[%X]",
        handlers=handlers,
        force=True,
    )
    # 静音 twitchio 太吵的 info
    logging.getLogger("twitchio").setLevel(logging.WARNING)
