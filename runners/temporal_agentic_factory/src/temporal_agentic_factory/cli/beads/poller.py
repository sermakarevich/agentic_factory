"""The `af beads` commands on single ticks: preview pulls, run one tick here."""

import json
from datetime import UTC, datetime
from typing import Annotated

import typer

from temporal_agentic_factory.cli.beads.opened import beads_failures, opened
from temporal_agentic_factory.cli.errors import fail, run_coro
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.client import BeadsClient
from temporal_agentic_factory.watchers.beads.models import PollSummary
from temporal_agentic_factory.watchers.beads.poll import poll_once
from temporal_agentic_factory.watchers.beads.temporal import TemporalWorkflows


def ready() -> None:
    """Show startable beads as JSON: what the next tick would pull."""
    client = opened()
    with beads_failures():
        beads = client.ready(settings.beads_poller.batch_limit)
    typer.echo(json.dumps([bead.model_dump() for bead in beads], indent=2))


def poll(
    once: Annotated[bool, typer.Option("--once", help="one tick now, then exit")] = False,
) -> None:
    """Run one poll tick in this process, for debugging; the ticks come from the
    schedule (`af beads start`)."""
    if not once:
        fail("the ticks come from the schedule: `af beads start`; `--once` runs one tick here")
    client = opened()
    typer.echo(run_coro(_ticked(client)).model_dump_json(indent=2))


async def _ticked(client: BeadsClient) -> PollSummary:
    """One tick with real beads and real workflows."""
    cfg = settings.beads_poller
    return await poll_once(
        client,
        TemporalWorkflows(),
        providers=list(settings.providers),
        batch_limit=cfg.batch_limit,
        orphan_timeout_sec=cfg.orphan_timeout_sec,
        now=datetime.now(UTC),
    )
