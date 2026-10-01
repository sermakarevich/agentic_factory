"""The `af beads` commands: preview pulls, run ticks, own the poll schedule."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

import typer
from temporalio.client import (
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleIntervalSpec,
    ScheduleSpec,
)
from temporalio.service import RPCError

from temporal_agentic_factory.cli.errors import run_coro
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.client import BeadsClient
from temporal_agentic_factory.watchers.beads.models import PollSummary
from temporal_agentic_factory.watchers.beads.poll import poll_once
from temporal_agentic_factory.watchers.beads.temporal import TemporalWorkflows
from temporal_agentic_factory.watchers.beads.workflow import BeadsPollWorkflow

beads_app = typer.Typer(
    no_args_is_help=True, help="Beads puller: ready beads in, job workflows out."
)


@beads_app.command(name="ready")
def ready() -> None:
    """Show startable beads as JSON: what the next tick would pull."""
    cfg = settings.beads_poller
    beads = BeadsClient(timeout_sec=cfg.command_timeout_sec).ready()
    typer.echo(json.dumps([bead.model_dump() for bead in beads], indent=2))


@beads_app.command(name="poll")
def poll(
    once: Annotated[bool, typer.Option("--once", help="one tick now, then exit")] = False,
    interval_sec: Annotated[
        int | None, typer.Option(help="daemon tick seconds; empty = settings")
    ] = None,
) -> None:
    """Run poll ticks in this process: once with --once, or a daemon loop.

    The daemon is for development; production ticks come from the schedule
    (`af beads schedule`), which survives this process dying.
    """
    cfg = settings.beads_poller
    if once:
        typer.echo(run_coro(_ticked()).model_dump_json(indent=2))
    else:
        run_coro(_loop(interval_sec or cfg.interval_sec))


async def _ticked() -> PollSummary:
    """One tick with real beads and real workflows."""
    cfg = settings.beads_poller
    return await poll_once(
        BeadsClient(timeout_sec=cfg.command_timeout_sec),
        TemporalWorkflows(),
        batch_limit=cfg.batch_limit,
        max_concurrent_jobs=settings.limits.max_concurrent_jobs,
        orphan_timeout_sec=cfg.orphan_timeout_sec,
        now=datetime.now(UTC),
    )


async def _loop(interval: int) -> None:
    """Tick forever; ctrl-c stops the loop, not the spawned workflows."""
    while True:
        summary = await _ticked()
        typer.echo(summary.model_dump_json(), err=True)
        await asyncio.sleep(interval)


@beads_app.command(name="schedule")
def schedule(
    interval_sec: Annotated[int | None, typer.Option(help="tick seconds; empty = settings")] = None,
) -> None:
    """Create or replace the Temporal Schedule that fires the poll workflow."""
    cfg = settings.beads_poller
    run_coro(_scheduled(interval_sec or cfg.interval_sec))
    typer.echo(f"scheduled {cfg.schedule_id}", err=True)


async def _scheduled(interval: int) -> None:
    cfg = settings.beads_poller
    client = await connect()
    action = ScheduleActionStartWorkflow(
        BeadsPollWorkflow.run,
        id=f"beads-poll-{uuid4().hex[:8]}",
        task_queue=settings.temporal.task_queue,
        static_summary="beads tick",
    )
    spec = ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(seconds=interval))])
    try:
        await client.get_schedule_handle(cfg.schedule_id).delete()
    except RPCError as error:
        if "not found" not in (error.message or "").lower():
            raise
    await client.create_schedule(cfg.schedule_id, Schedule(action=action, spec=spec))


@beads_app.command(name="unschedule")
def unschedule() -> None:
    """Delete the poll schedule; already-spawned workflows keep running."""
    run_coro(_unscheduled())
    typer.echo(f"unscheduled {settings.beads_poller.schedule_id}", err=True)


async def _unscheduled() -> None:
    client = await connect()
    try:
        await client.get_schedule_handle(settings.beads_poller.schedule_id).delete()
    except RPCError as error:
        if "not found" not in (error.message or "").lower():
            raise
