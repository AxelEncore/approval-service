"""Structured (JSON) logging configuration."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.context import request_id_var, user_id_var, workspace_id_var
from app.core.sanitization import sanitize

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Render each log record as a single sanitized JSON object."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        workspace_id = workspace_id_var.get()
        if workspace_id:
            payload["workspace_id"] = workspace_id
        user_id = user_id_var.get()
        if user_id:
            payload["user_id"] = user_id

        # Structured fields passed via ``extra={"extra_fields": {...}}``.
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)

        # Any other ad-hoc attributes attached to the record.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in ("extra_fields",):
                payload.setdefault(key, value)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(sanitize(payload), default=str, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Route uvicorn loggers through our JSON handler too.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.propagate = False


def log_event(logger: logging.Logger, message: str, **fields: Any) -> None:
    """Emit a structured log line; ``fields`` are sanitized by the formatter."""
    logger.info(message, extra={"extra_fields": sanitize(fields)})
