"""The `af cleaner` commands on the cleaner schedule: start, stop, restart, status, run."""

import typer

from temporal_agentic_factory.cleaner.clean import cleaned
from temporal_agentic_factory.cleaner.schedule import (
    cleaner_schedule_status,
    start_cleaner_schedule,
)
from temporal_agentic_factory.cleaner.workflow import CleanConfig
from temporal_agentic_factory.cli.errors import run_coro
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.schedules import delete_schedule
from temporal_agentic_factory.settings.load import settings

cleaner_app = typer.Typer(
    no_args_is_help=True,
    help="Cleaner: a schedule that deletes old closed runs by the per-type rules in its settings.",
)


@cleaner_app.command()
def start() -> None:
    """Create or replace the cleaner schedule with the configured rules; prints its id."""
    replaced = run_coro(_started())
    schedule_id = settings.cleaner.schedule_id
    typer.echo(f"{'replaced' if replaced else 'created'}: {schedule_id}", err=True)
    typer.echo(schedule_id)


async def _started() -> bool:
    cfg = settings.cleaner
    return await start_cleaner_schedule(
        await connect(),
        cfg.schedule_id,
        settings.temporal.task_queue,
        cfg.interval_sec,
        configured_clean(),
    )


def configured_clean() -> CleanConfig:
    """One run's rules and timeout from `[cleaner]`."""
    return CleanConfig(rules=settings.cleaner.rules, timeout_sec=settings.cleaner.timeout_sec)


@cleaner_app.command()
def stop() -> None:
    """Delete the cleaner schedule; a running clean finishes, nothing else is touched."""
    deleted = run_coro(_stopped())
    typer.echo(
        f"{'deleted' if deleted else 'no schedule'}: {settings.cleaner.schedule_id}", err=True
    )


async def _stopped() -> bool:
    client = await connect()
    return await delete_schedule(client.get_schedule_handle(settings.cleaner.schedule_id))


@cleaner_app.command()
def restart() -> None:
    """Stop, then start the cleaner schedule: picks up a change to its settings and rules."""
    stop()
    start()


@cleaner_app.command()
def status() -> None:
    """The schedule as JSON: exists, paused, interval, next run, last run and what it deleted."""
    typer.echo(run_coro(_status_json()))


async def _status_json() -> str:
    found = await cleaner_schedule_status(await connect(), settings.cleaner.schedule_id)
    return found.model_dump_json(indent=2)


@cleaner_app.command(name="run")
def run_once() -> None:
    """One clean now, in this process, with the configured rules; prints what it deleted."""
    typer.echo(run_coro(_cleaned_json()))


async def _cleaned_json() -> str:
    summary = await cleaned(await connect(), settings.temporal.namespace, settings.cleaner.rules)
    return summary.model_dump_json(indent=2)
