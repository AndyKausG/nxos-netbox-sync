"""
Change logger for netbox-sync.
Logs ONLY when changes are applied (FAIL list non-empty or --apply executed).
Uses stdlib RotatingFileHandler. If LOG_FILE not set: stdout only.

Log format: 2026-04-14T12:00:00 [netbox-sync.core-sw] description
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_root_logger_configured = False


def _configure_root_logger():
    global _root_logger_configured
    if _root_logger_configured:
        return

    log_file = os.environ.get("LOG_FILE")
    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler = (
        RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)
        if log_file
        else logging.StreamHandler(sys.stdout)
    )
    handler.setFormatter(fmt)

    root = logging.getLogger("netbox-sync")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    _root_logger_configured = True


def log_change(device: str, description: str):
    """Log a single applied change. Call only when a change is actually applied."""
    _configure_root_logger()
    logging.getLogger(f"netbox-sync.{device}").info(description)
