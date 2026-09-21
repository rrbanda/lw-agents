"""Structured logging configuration using structlog.

Provides JSON output mode for container/CI environments and colored
console output for local development. Context variables (run_id,
agent_name, cve_id) flow into every log line automatically.

Usage:
    from app.logging_config import configure_logging, get_logger
    configure_logging()  # call once at startup
    log = get_logger()
    log.info("cve_selected", cve_id="CVE-2024-1234", score=0.87)
"""

from __future__ import annotations

import logging
import os
import re
import sys

import structlog

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\].*?\x07")


class _TeeWriter:
    """Write to two streams simultaneously.

    The secondary (log file) stream receives cleaned output: ANSI escape
    sequences are stripped.
    """

    def __init__(self, primary, secondary):
        self._primary = primary
        self._secondary = secondary

    def write(self, data):
        self._primary.write(data)
        clean = _ANSI_RE.sub("", data)
        if clean.strip():
            self._secondary.write(clean)

    def flush(self):
        self._primary.flush()
        self._secondary.flush()

    def isatty(self):
        return self._primary.isatty()


def configure_logging(
    json_output: bool | None = None,
    level: int = logging.INFO,
) -> None:
    """Set up structlog with a ProcessorFormatter bridge for stdlib compatibility.

    Args:
        json_output: If True, emit JSON lines. If None, auto-detect
            (JSON in CI/container, console in TTY).
        level: Root log level.
    """
    if json_output is None:
        json_output = bool(os.environ.get("CI")) or not sys.stderr.isatty()

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("google.adk").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger (convenience wrapper)."""
    return structlog.get_logger(name)


def bind_run_context(
    *,
    run_id: str = "",
    agent_name: str = "",
    cve_id: str = "",
    **extra,
) -> None:
    """Bind context variables that flow into every subsequent log line.

    Call at the start of a pipeline run or when entering an agent.
    """
    ctx = {}
    if run_id:
        ctx["run_id"] = run_id
    if agent_name:
        ctx["agent"] = agent_name
    if cve_id:
        ctx["cve_id"] = cve_id
    ctx.update(extra)
    structlog.contextvars.bind_contextvars(**ctx)


def clear_run_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()


def add_file_handler(log_path: str) -> None:
    """Add a file handler to the root logger for run log persistence.

    Uses plain text (no color) so the log file is machine-readable.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        foreign_pre_chain=shared_processors,
    )

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(formatter)
    logging.getLogger().addHandler(fh)


def setup_tee_logging(log_path: str) -> None:
    """Set up dual console + file logging (tee pattern).

    Console gets colored output; file gets clean text.
    """
    add_file_handler(log_path)
