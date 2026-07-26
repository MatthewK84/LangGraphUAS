"""Centralized logging configuration."""

import logging
from typing import Final

_LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str) -> None:
    """Configure root logging once at startup.

    Args:
        level: A logging level name such as ``INFO`` or ``DEBUG``.
    """
    resolved: int = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    logging.basicConfig(level=resolved, format=_LOG_FORMAT)
