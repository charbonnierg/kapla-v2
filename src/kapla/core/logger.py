from __future__ import annotations

import logging
import os
from logging import NOTSET
from typing import Optional

import structlog


def configure_logger(level: Optional[int] = None) -> None:
    """Configure structlog logger. Level cannot be changed once it is set.

    Note: Using a static logging level leads to faster logging operations in production.
    """
    # Check that the logging level exists
    # Optionally fetch logging level from environment variable
    if level is None:
        level_str = os.environ.get("LOGGING_LEVEL", NOTSET)
        level = logging.getLevelName(level_str)
        if not isinstance(level, int):
            raise ValueError(f"Logging level not supported: {level}")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


logger = structlog.get_logger()
