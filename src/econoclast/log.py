"""Rich-backed logging and a shared console for the whole package."""

from __future__ import annotations

import logging
import os

from rich.console import Console
from rich.logging import RichHandler

console = Console(stderr=True)

_CONFIGURED = False


def setup_logging(level: str | int | None = None) -> None:
    """Configure root logging with a Rich handler. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        if level is not None:
            logging.getLogger("econoclast").setLevel(_coerce_level(level))
        return

    resolved = _coerce_level(level if level is not None else os.getenv("ECONOCLAST_LOG_LEVEL", "INFO"))
    handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        show_path=False,
        markup=True,
        omit_repeated_times=False,
    )
    logging.basicConfig(
        level=resolved,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
    )
    # Quiet noisy third parties.
    for noisy in ("httpx", "httpcore", "urllib3", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _CONFIGURED = True


def _coerce_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    return getattr(logging, str(level).upper(), logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger; ensures logging is configured."""
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(f"econoclast.{name}")
