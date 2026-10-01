"""The `af beads` commands on the watcher workflow: start, stop, restart, status."""

import typer

from temporal_agentic_factory.cli.beads.opened import opened
from temporal_agentic_factory.cli.errors import fail, run_coro
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.control import (
    start_watcher,
    stop_watcher,
    watcher_status,
)
from temporal_agentic_factory.watchers.beads.legacy import (
    LEGACY_SCHEDULE_ID,
    deleted_legacy_schedule,
)
from temporal_agentic_factory.watchers.beads.workflow import WatcherConfig
from temporal_agentic_factory.workflows.job import search_attributes


def start() -> None:
    """Start the beads watcher; one already running is fine. Prints its id.

    Also deletes the legacy `beads-poll` schedule and registers missing search
    attributes, so the watcher's `LastCheck` upserts are accepted."""
    opened()
    for line in run_coro(_started()):
        typer.echo(line, err=True)
    typer.echo(settings.beads_watcher.workflow_id)


async def _started() -> list[str]:
    """What starting did, one line each."""
    client = await connect()
    lines = []
    if await deleted_legacy_schedule(client):
        lines.append(f"deleted the legacy schedule {LEGACY_SCHEDULE_ID}")
    added = await search_attributes.register(client, settings.temporal.namespace)
    if added:
        lines.append(f"registered attributes {', '.join(added)}")
    cfg = settings.beads_watcher
    started = await start_watcher(
        client, cfg.workflow_id, settings.temporal.task_queue, configured_watcher()
    )
    lines.append(f"{'started' if started else 'already running'}: {cfg.workflow_id}")
    return lines


def configured_watcher() -> WatcherConfig:
    """The loop's knobs from `[beads_watcher]`."""
    cfg = settings.beads_watcher
    return WatcherConfig(
        interval_sec=cfg.interval_sec,
        tick_timeout_sec=cfg.tick_timeout_sec,
        trim_timeout_sec=cfg.trim_timeout_sec,
        checks_per_run=cfg.checks_per_run,
    )


def stop() -> None:
    """Cancel the beads watcher and wait up to `[beads_watcher] stop_wait_sec` for it to end."""
    cfg = settings.beads_watcher
    if not run_coro(_stopped()):
        fail(
            f"{cfg.workflow_id} still runs after {cfg.stop_wait_sec}s (is a runner up?);"
            f" `af terminate {cfg.workflow_id}` ends it now"
        )
    typer.echo(f"stopped: {cfg.workflow_id}", err=True)


async def _stopped() -> bool:
    cfg = settings.beads_watcher
    return await stop_watcher(await connect(), cfg.workflow_id, cfg.stop_wait_sec)


def restart() -> None:
    """Stop, then start the beads watcher: needed after a change to its loop or its settings."""
    stop()
    start()


def status() -> None:
    """Whether the beads watcher runs, and its last check, as JSON."""
    typer.echo(run_coro(_status_json()))


async def _status_json() -> str:
    cfg = settings.beads_watcher
    found = await watcher_status(await connect(), cfg.workflow_id, cfg.query_timeout_sec)
    return found.model_dump_json(indent=2)
