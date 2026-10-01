"""The beads watcher: one long-running workflow that ticks, sleeps and repeats.

The loop is frozen: it must replay across code changes, so every change to
what a tick does goes into the activities (`tick.py`, `poll.py`), and a change
to this loop needs `af beads restart`. Its knobs come in as the input, so a
settings change also takes a restart. After `checks_per_run` ticks, or when
Temporal suggests it, the run continues as new with the last check carried
over; old runs are trimmed at the first start and before each new run.
"""

from datetime import timedelta

from pydantic import BaseModel
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporalio.exceptions import ActivityError, is_cancelled_exception

    from temporal_agentic_factory.watchers.beads.last_check import (
        LastCheck,
        check_of,
        failed_check,
    )
    from temporal_agentic_factory.watchers.beads.tick import BeadsPollActivity
    from temporal_agentic_factory.watchers.beads.trim import trim_watcher_runs
    from temporal_agentic_factory.workflows.job.search_attributes import LAST_CHECK


class WatcherConfig(BaseModel):
    """The loop's knobs, from `[beads_watcher]` when `af beads start` starts it."""

    interval_sec: int
    tick_timeout_sec: int
    trim_timeout_sec: int
    checks_per_run: int


class WatcherRun(BaseModel):
    """What one watcher run starts from: its knobs and the check the last run ended on."""

    config: WatcherConfig
    last_check: LastCheck | None = None


@workflow.defn(name="beads_watcher")
class BeadsWatcherWorkflow:
    """Tick, sleep, repeat; continue as new after a run's worth of ticks."""

    def __init__(self) -> None:
        self._last: LastCheck | None = None

    @workflow.run
    async def run(self, watch: WatcherRun) -> None:
        self._last = watch.last_check
        if workflow.info().continued_run_id is None:
            await _trimmed(watch.config)
        await self._checks(watch.config)
        await _trimmed(watch.config)
        workflow.continue_as_new(watch.model_copy(update={"last_check": self._last}))

    @workflow.query(name="last_check")
    def last_check(self) -> LastCheck | None:
        """The last tick's summary; None before the first one."""
        return self._last

    async def _checks(self, config: WatcherConfig) -> None:
        """Up to `checks_per_run` ticks, each followed by the interval."""
        for _ in range(config.checks_per_run):
            self._remember(await _checked(config))
            await workflow.sleep(config.interval_sec)
            if workflow.info().is_continue_as_new_suggested():
                return

    def _remember(self, check: LastCheck) -> None:
        """The check kept for the query; the attribute upserted only when its line changes."""
        if self._last is None or self._last.line() != check.line():
            workflow.upsert_search_attributes([LAST_CHECK.value_set(check.line())])
        self._last = check


async def _checked(config: WatcherConfig) -> LastCheck:
    """One tick; a tick that fails after its retries is a failed check, not a failed loop."""
    try:
        summary = await workflow.execute_activity_method(
            BeadsPollActivity.poll,
            start_to_close_timeout=timedelta(seconds=config.tick_timeout_sec),
            retry_policy=RetryPolicy(maximum_attempts=2),
            summary="beads tick",
        )
    except ActivityError as error:
        if is_cancelled_exception(error):
            raise
        return failed_check(workflow.now(), str(error.cause or error))
    return check_of(workflow.now(), summary)


async def _trimmed(config: WatcherConfig) -> None:
    """Old watcher runs deleted; best effort, so a failure is ignored."""
    try:
        await workflow.execute_activity(
            trim_watcher_runs,
            start_to_close_timeout=timedelta(seconds=config.trim_timeout_sec),
            retry_policy=RetryPolicy(maximum_attempts=1),  # best effort: the next trim catches up
            summary="trim watcher runs",
        )
    except ActivityError as error:
        if is_cancelled_exception(error):
            raise
