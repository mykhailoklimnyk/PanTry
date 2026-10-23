from __future__ import annotations

import logging
import sys

import structlog

from komora.config import settings

_configured = False

_URL_LOGGERS = ("httpx2", "httpx", "httpcore")


def quiet_url_logs() -> None:
    for name in _URL_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def setup_logging(*, json_output: bool | None = None) -> None:
    global _configured
    if _configured:
        return

    if json_output is None:
        json_output = not sys.stderr.isatty()

    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=settings.log_level.upper())
    quiet_url_logs()

    renderer = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper())
        ),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    setup_logging()
    return structlog.get_logger(name)
