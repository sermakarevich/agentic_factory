"""The `af` typer app: every command registered on one entry point."""

import logging

import typer

from agentic_factory.logging_setup import configure_logging
from temporal_agentic_factory.cli import workflows
from temporal_agentic_factory.cli.beads import beads_app
from temporal_agentic_factory.cli.coders import coders
from temporal_agentic_factory.cli.distill import distill
from temporal_agentic_factory.cli.errors import run_coro
from temporal_agentic_factory.cli.job import run
from temporal_agentic_factory.cli.research import research
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.identity import runner_identity
from temporal_agentic_factory.runner import serve
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.workflows.job import search_attributes

app = typer.Typer(no_args_is_help=True, help="af: agentic_factory on Temporal.")


@app.command()
def runner(debug: bool = False) -> None:
    """Start a process that polls the main task queue: every workflow and the
    quick activities. Coder jobs run in `af coders`."""
    configure_logging(logging.DEBUG if debug else logging.INFO)
    identity = runner_identity()
    typer.echo(f"runner {identity}", err=True)
    run_coro(serve(identity))


@app.command(name="worker")
def worker(debug: bool = False) -> None:
    """Alias of `runner`: start a process that polls the main task queue."""
    runner(debug=debug)


@app.command()
def attributes() -> None:
    """Register the search attributes (Name, Provider, ...) on the server, once per server.
    The UI then offers them as columns and filters."""
    added = run_coro(_registered_attributes())
    typer.echo(f"added {', '.join(added)}" if added else "all attributes were registered already")


async def _registered_attributes() -> list[str]:
    return await search_attributes.register(await connect(), settings.temporal.namespace)


app.command()(coders)
app.command()(run)
app.command()(distill)
app.command()(research)
app.command(name="status")(workflows.status)
app.command(name="describe")(workflows.status)
app.command(name="result")(workflows.result)
app.command(name="list")(workflows.list_workflows)
app.command(name="cancel")(workflows.cancel)
app.command(name="terminate")(workflows.terminate)
app.command(name="health")(workflows.health)
app.add_typer(beads_app, name="beads")
