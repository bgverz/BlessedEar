"""
Structured logging configuration for BlessedEar.

In production (LOG_FORMAT=json or when not in debug mode) logs are emitted
as newline-delimited JSON so they can be ingested by any log aggregator
(Datadog, CloudWatch, ELK, etc.).

In development (DEBUG=true) logs use a human-readable format by default.

Usage — call configure_logging() once at application startup (main.py):
    from app.core.logging_config import configure_logging
    configure_logging()
"""

import logging
import sys
import json
import time
from typing import Any


class JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key, val in record.__dict__.items():
            if key not in {
                "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno",
                "funcName", "created", "msecs", "relativeCreated", "thread",
                "threadName", "processName", "process", "name", "message",
            }:
                payload[key] = val
        return json.dumps(payload, default=str)


def configure_logging(log_level: str = "INFO", use_json: bool = True) -> None:
    """Configure root logger.  Call once at startup before any log output."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    if use_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("spotipy").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
