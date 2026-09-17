"""Structured logging via structlog, bridged with stdlib logging.

Development renders human-readable console output; staging/production
render JSON lines suitable for log aggregators. Every log record is
correlated with the request id bound by the request-context middleware.
"""

from __future__ import annotations

import logging
import sys

import structlog

_configured = False


def setup_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    """Configure structlog + stdlib logging. Safe to call repeatedly (idempotent)."""
    global _configured
    if _configured:
        return

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    # Pre-chain applied to records originating from third-party libraries.
    pre_chain: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        timestamper,
        structlog.stdlib.ExtraAdder(),
    ]

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=pre_chain,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Tame noisy third-party loggers.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger for the given namespace."""
    return structlog.get_logger(name)
