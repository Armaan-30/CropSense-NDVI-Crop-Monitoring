"""Logging configuration for the CropSense backend.

A single call to :func:`configure_logging` at application start-up sets up a
consistent, timestamped format for the application logger tree and quiets the
very chatty Google API client libraries that Earth Engine pulls in.
"""

from __future__ import annotations

import logging
import sys

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

# Libraries that log at INFO/DEBUG far more than we want to see.
_NOISY_LOGGERS = (
    "googleapiclient",
    "googleapiclient.discovery_cache",
    "google.auth",
    "google_auth_httplib2",
    "urllib3",
    "urllib3.connectionpool",
)

_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Install a stream handler on the root logger.

    Idempotent: repeated calls only update the level, so importing the app
    twice (e.g. in tests) does not duplicate log lines.

    Args:
        level: Log level name, e.g. ``"INFO"`` or ``"DEBUG"``.
    """
    global _configured

    resolved = getattr(logging, level.upper(), logging.INFO)

    if not _configured:
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT))
        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(handler)
        _configured = True

    logging.getLogger().setLevel(resolved)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(max(resolved, logging.WARNING))


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger for a module.

    Args:
        name: Usually ``__name__`` of the calling module.
    """
    return logging.getLogger(name)
