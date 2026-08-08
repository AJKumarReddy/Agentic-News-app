"""Structured JSON logging.

Every log line is a single JSON object so it can be shipped to CloudWatch or
any log aggregator without extra parsing. Secrets are never logged: the
formatter only serializes explicitly passed fields.
"""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_REDACT_KEYS = {"api_key", "api-key", "authorization", "password", "secret", "token"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        extra = getattr(record, "event_fields", None)
        if extra:
            for key, value in extra.items():
                if key.lower() in _REDACT_KEYS:
                    payload[key] = "[redacted]"
                else:
                    payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def log_event(logger: logging.Logger, message: str, level: int = logging.INFO, **fields: Any) -> None:
    """Log a structured event: log_event(log, "rag_retrieval", retrieved_chunks=12, latency_ms=88)."""
    logger.log(level, message, extra={"event_fields": fields})


def new_request_id() -> str:
    rid = uuid.uuid4().hex[:16]
    request_id_var.set(rid)
    return rid


class Timer:
    """Context manager measuring elapsed milliseconds for latency logging."""

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        self.ms = 0.0
        return self

    def __exit__(self, *exc: Any) -> None:
        self.ms = round((time.perf_counter() - self._start) * 1000, 1)
