"""Logging configuration for Argos."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from core.config import get_settings

settings = get_settings()

# Remove default handler
logger.remove()

# Console handler — colored, compact
logger.add(
    sys.stderr,
    level="DEBUG" if settings.env == "development" else "INFO",
    format=(
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    ),
    colorize=True,
)

# File handler — structured rotation
log_dir = settings.data_dir / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
logger.add(
    log_dir / "argos_{time:YYYY-MM-DD}.log",
    rotation="10 MB",
    retention="30 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
    serialize=False,
    compression="gz",
)

__all__ = ["logger"]
