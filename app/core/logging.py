"""
Structured logging with GCP Cloud Logging integration.

On Cloud Run, logs written to stdout in JSON format are automatically
ingested by GCP Cloud Logging. This module configures Python's standard
logging to emit structured JSON and optionally attaches a GCP Cloud
Logging handler for enriched log entries (trace IDs, resource labels, etc.).

Usage:
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("User logged in", extra={"user_id": "abc123", "env": "production"})
"""

import json
import logging
import sys
from typing import Any

from app.core.config import settings


# =============================================================================
# JSON Formatter — emits structured log records compatible with GCP Logging
# =============================================================================

class GCPStructuredFormatter(logging.Formatter):
    """
    Formats log records as newline-delimited JSON compatible with GCP Cloud Logging.

    GCP automatically maps the following fields:
      - "severity"  → log severity level (replaces "levelname")
      - "message"   → log body
      - "timestamp" → ISO 8601 timestamp
      - "logging.googleapis.com/trace" → trace ID for request correlation
    """

    # Map Python log levels to GCP severity labels
    SEVERITY_MAP: dict[int, str] = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARNING",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "severity": self.SEVERITY_MAP.get(record.levelno, "DEFAULT"),
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "timestamp": self.formatTime(record, self.datefmt),
            "environment": settings.APP_ENV,
            "app_version": settings.APP_VERSION,
        }

        # Attach exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Attach any extra fields passed via extra={} in logger calls
        skip_keys = {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "id", "levelname", "levelno", "lineno", "module",
            "msecs", "message", "msg", "name", "pathname", "process",
            "processName", "relativeCreated", "stack_info", "thread", "threadName",
        }
        for key, value in record.__dict__.items():
            if key not in skip_keys and not key.startswith("_"):
                log_entry[key] = value

        return json.dumps(log_entry, default=str, ensure_ascii=False)


# =============================================================================
# GCP Cloud Logging Handler (optional enriched integration)
# =============================================================================

def _try_attach_gcp_handler(logger: logging.Logger) -> None:
    """
    Attempt to attach google-cloud-logging handler for enriched GCP integration.

    Falls back silently if:
    - GCP SDK is not available
    - Application credentials are not configured (e.g., local dev without ADC)
    - ENABLE_GCP_LOGGING is False
    """
    if not settings.ENABLE_GCP_LOGGING:
        return

    try:
        import google.cloud.logging  # type: ignore[import-untyped]

        client = google.cloud.logging.Client(project=settings.GCP_PROJECT_ID or None)
        # Attach the GCP handler — this sends structured logs to Cloud Logging API
        # On Cloud Run, stdout JSON is sufficient; this adds resource labels + trace linking
        client.setup_logging(log_level=getattr(logging, settings.LOG_LEVEL))
        logger.info(
            "GCP Cloud Logging handler attached",
            extra={"gcp_project": settings.GCP_PROJECT_ID},
        )
    except Exception as exc:  # noqa: BLE001
        # Never fail startup due to logging misconfiguration
        logger.warning(f"Could not attach GCP Cloud Logging handler: {exc}")


# =============================================================================
# Logger Factory
# =============================================================================

def configure_logging() -> None:
    """
    Configure the root logger for the application.

    Call once at application startup (in main.py lifespan).
    All subsequent calls to get_logger() will inherit this configuration.
    """
    log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)

    # Remove any existing handlers from root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # JSON structured handler → stdout (picked up by GCP Cloud Logging on Cloud Run)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(GCPStructuredFormatter())
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # Optionally attach GCP Cloud Logging SDK handler
    app_logger = logging.getLogger("app")
    _try_attach_gcp_handler(app_logger)


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger instance.

    Args:
        name: Logger name — use __name__ for module-level loggers.

    Returns:
        Configured logging.Logger instance.

    Example:
        logger = get_logger(__name__)
        logger.info("Processing request", extra={"request_id": "xyz"})
    """
    return logging.getLogger(name)
