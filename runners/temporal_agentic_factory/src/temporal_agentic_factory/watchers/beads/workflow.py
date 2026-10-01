"""The beads poll: one tick, then a trim of old runs; the `beads-poll` Schedule starts it.

The tick's summary is the run's result, so the UI shows what the tick did. A
tick that fails after its retries still runs the trim, then fails the run.
Its timeouts come in as the input, set by `af beads start` from `[beads_poller]`.
"""

from datetime import timedelta

from pydantic import BaseModel
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporalio.exceptions import ActivityError, is_cancelled_exception

    from temporal_agentic_factory.watchers.beads.models import PollSummary
    from temporal_agentic_factory.watchers.beads.tick import BeadsPollActivity
    from temporal_agentic_factory.watchers.beads.trim import trim_poll_runs


class PollConfig(BaseModel):
    """One run's timeouts, from `[beads_poller]` in the schedule's action."""

    tick_timeout_sec: int
    trim_timeout_sec: int


@workflow.defn(name="beads_poll")
class BeadsPollWorkflow:
    """One tick, then the trim; the tick's summary is the result."""

    @workflow.run
    async def run(self, config: PollConfig) -> PollSummary:
        try:
            return await _ticked(config)
        finally:
            await _trimmed(config)


async def _ticked(config: PollConfig) -> PollSummary:
    """One reconcile-and-spawn pass; a failure after its retries fails the run."""
    return await workflow.execute_activity_method(
        BeadsPollActivity.poll,
        start_to_close_timeout=timedelta(seconds=config.tick_timeout_sec),
        retry_policy=RetryPolicy(maximum_attempts=2),
        summary="beads tick",
    )


async def _trimmed(config: PollConfig) -> None:
    """Old poll runs deleted; best effort, so a failure is ignored."""
    try:
        await workflow.execute_activity(
            trim_poll_runs,
            start_to_close_timeout=timedelta(seconds=config.trim_timeout_sec),
            retry_policy=RetryPolicy(maximum_attempts=1),  # best effort: the next trim catches up
            summary="trim poll runs",
        )
    except ActivityError as error:
        if is_cancelled_exception(error):
            raise
