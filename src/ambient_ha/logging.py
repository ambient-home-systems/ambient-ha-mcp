"""Structured logging with defense-in-depth secret redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

_REDACTION_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;\"']+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)((?:token|password|api[_-]?key)\s*[:=]\s*)[^\s,;\"']+"),
)


def redact_secrets(value: object) -> str:
    """Redact common credential forms from a value before it is emitted."""
    redacted = str(value)
    for pattern in _REDACTION_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


class JsonFormatter(logging.Formatter):
    """Emit one safe JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def configure_logging(level: str) -> None:
    """Configure process logging once with safe structured output."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
