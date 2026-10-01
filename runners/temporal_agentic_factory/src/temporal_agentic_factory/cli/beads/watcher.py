"""The `af beads` commands on the poll schedule: start, stop, restart, status."""

import typer

from temporal_agentic_factory.cli.beads.opened import opened
from temporal_agentic_factory.cli.errors import run_coro
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.schedules import delete_schedule
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.control import (
    OLD_WATCHER_ID,
    end_old_watcher,
    poll_schedule_status,
    start_poll_schedule,
)
from temporal_agentic_factory.watchers.beads.workflow import PollConfig
from temporal_agentic_factory.workflows.job import search_attributes


def start() -> None:
    """Create or replace the beads poll schedule; prints its id.

    Also ends the old long-running `beads-watcher` workflow and registers
    missing search attributes, so the spawned jobs' columns are accepted."""
    opened()
    for line in run_coro(_started()):
        typer.echo(line, err=True)
    typer.echo(settings.beads_poller.schedule_id)


async def _started() -> list[str]:
    """What starting did, one line each."""
    client = await connect()
    cfg = settings.beads_poller
    lines = []
    added = await search_attributes.register(client, settings.temporal.namespace)
    if added:
        lines.append(f"registered attributes {', '.join(added)}")
    replaced = await start_poll_schedule(
        client, cfg.schedule_id, settings.temporal.task_queue, cfg.interval_sec, configured_poll()
    )
    lines.append(f"{'replaced' if replaced else 'created'}: {cfg.schedule_id}")
    if await end_old_watcher(client):
        lines.append(f"terminated the old watcher {OLD_WATCHER_ID}")
    return lines


def configured_poll() -> PollConfig:
    """One run's timeout from `[beads_poller]`."""
    return PollConfig(tick_timeout_sec=settings.beads_poller.tick_timeout_sec)


def stop() -> None:
    """Delete the beads poll schedule; a running tick finishes, spawned jobs keep running."""
    schedule_id = settings.beads_poller.schedule_id
    deleted = run_coro(_stopped())
    typer.echo(f"{'deleted' if deleted else 'no schedule'}: {schedule_id}", err=True)


async def _stopped() -> bool:
    client = await connect()
    return await delete_schedule(client.get_schedule_handle(settings.beads_poller.schedule_id))


def restart() -> None:
    """Stop, then start the beads poll schedule: picks up a change to its settings."""
    stop()
    start()


def status() -> None:
    """The schedule as JSON: exists, paused, interval, next run, last run and what it did."""
    typer.echo(run_coro(_status_json()))


async def _status_json() -> str:
    found = await poll_schedule_status(await connect(), settings.beads_poller.schedule_id)
    return found.model_dump_json(indent=2)
