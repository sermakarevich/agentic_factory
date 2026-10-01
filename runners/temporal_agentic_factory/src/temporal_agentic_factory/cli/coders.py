"""The `coders` command: the one process that runs coder jobs on this machine."""

import logging

import typer

from agentic_factory.logging_setup import configure_logging
from temporal_agentic_factory.cli.errors import fail, run_coro
from temporal_agentic_factory.coders import serve_coders
from temporal_agentic_factory.identity import runner_identity
from temporal_agentic_factory.other_coders import other_coders_pids


def coders(debug: bool = False) -> None:
    """Start the one process that runs coder jobs: a worker per configured
    provider on its coder queue, with that provider's limit. Refused while
    another one runs on this machine, since the limits hold per process."""
    others = other_coders_pids()
    if others:
        fail(
            f"another `factory coders` process is already running (pid {others[0]});"
            " stop it first: just coders-stop"
        )
    configure_logging(logging.DEBUG if debug else logging.INFO)
    identity = runner_identity()
    typer.echo(f"coders {identity}", err=True)
    run_coro(serve_coders(identity))
