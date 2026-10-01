import asyncio
from typing import Any

import typer
from temporalio.client import Client, WorkflowHandle
from temporalio.contrib.pydantic import pydantic_data_converter

from temporal_agentic_factory.settings.load import settings


async def connect() -> Client:
    """A client on the configured server. Pydantic models travel as they are."""
    return await Client.connect(
        settings.temporal.address,
        namespace=settings.temporal.namespace,
        data_converter=pydantic_data_converter,
    )


async def awaited[T](handle: WorkflowHandle[Any, T]) -> T:
    """The workflow's result; ctrl-c stops the run, not just the wait."""
    typer.echo(f"started {handle.id}", err=True)
    try:
        return await handle.result()
    except asyncio.CancelledError:
        await handle.cancel()
        raise
