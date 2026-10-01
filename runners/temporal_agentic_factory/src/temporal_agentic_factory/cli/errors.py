"""Clean failures for every `af` command: one stderr line and exit 1, no traceback."""

import asyncio
from collections.abc import Coroutine
from typing import Any, NoReturn

import typer
from temporalio.service import RPCError

STATUSES = (
    "Running",
    "Completed",
    "Failed",
    "Canceled",
    "Terminated",
    "ContinuingAsNew",
    "TimedOut",
)

WORKFLOW_TYPES = ("job", "job_with_structured_output", "distill", "beads_watcher")


def normalize_status(value: str) -> str:
    """`running` -> `Running`; anything unknown names the valid values (exit 2)."""
    for valid in STATUSES:
        if value.lower() == valid.lower():
            return valid
    raise typer.BadParameter(f"{value!r}: want one of {', '.join(STATUSES)}")


def normalize_workflow_type(value: str) -> str:
    """`Job` -> `job`; anything unknown names the valid values (exit 2)."""
    for valid in WORKFLOW_TYPES:
        if value.lower() == valid.lower():
            return valid
    raise typer.BadParameter(f"{value!r}: want one of {', '.join(WORKFLOW_TYPES)}")


def run_coro[T](coro: Coroutine[Any, Any, T]) -> T:
    """`asyncio.run`, with Temporal and connection failures as a clean error.

    Cancel and keyboard interrupts pass through untouched; everything else
    becomes `af: error: ...` on stderr with exit 1.
    """
    try:
        return asyncio.run(coro)
    except RPCError as error:
        fail(error.message or str(error))
    except Exception as error:
        fail(str(error) or type(error).__name__)


def fail(message: str) -> NoReturn:
    """One stderr line and exit 1."""
    typer.echo(f"af: error: {message}", err=True)
    raise typer.Exit(1)
