"""Logging utilities for the Streamlit app."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "stock_app.log"

_BASE_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def get_logger(name: str = "stock_app") -> logging.Logger:
    """Return a logger configured with rotating file + console handlers."""

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(_BASE_FORMAT)
    file_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.propagate = False
    return logger


def read_recent_logs(max_lines: int = 200) -> str:
    """Return the last *max_lines* lines from the log file."""

    if not LOG_PATH.exists():
        return "Log file not created yet. Trigger an action to generate entries."

    try:
        with LOG_PATH.open("r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except OSError as exc:
        return f"Unable to read log file: {exc}"

    tail = lines[-max_lines:]
    return "".join(tail).strip() or "Log file is currently empty."

