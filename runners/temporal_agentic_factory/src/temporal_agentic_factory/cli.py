"""The `factory` command: the runner process, the UI columns, and the subject
commands (`run`, `distill`) registered from their modules."""

import asyncio
import logging

import typer

from agentic_factory.logging_setup import configure_logging
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.distill.cli import distill
from temporal_agentic_factory.identity import runner_identity
from temporal_agentic_factory.job import search_attributes
from temporal_agentic_factory.job.cli import run
from temporal_agentic_factory.research.cli import research
from temporal_agentic_factory.runner import serve
from temporal_agentic_factory.settings.load import settings

app = typer.Typer(no_args_is_help=True, help="agentic_factory on Temporal.")


@app.command()
def runner(debug: bool = False) -> None:
    """Start the process that polls Temporal task queues."""
    configure_logging(logging.DEBUG if debug else logging.INFO)
    identity = runner_identity()
    typer.echo(f"runner {identity}", err=True)
    asyncio.run(serve(identity))


@app.command()
def attributes() -> None:
    """Register the job's search attributes on the server, once per server.
    The UI then offers them as columns and filters."""
    added = asyncio.run(_registered_attributes())
    typer.echo(f"added {', '.join(added)}" if added else "all attributes were registered already")


async def _registered_attributes() -> list[str]:
    return await search_attributes.register(await connect(), settings.temporal.namespace)


app.command()(run)
app.command()(distill)
app.command()(research)
