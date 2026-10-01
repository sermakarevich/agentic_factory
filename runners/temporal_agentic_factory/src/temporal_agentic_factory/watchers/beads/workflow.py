"""The beads poll: one tick; the `beads-poll` Schedule starts it.

The tick's summary is the run's result, so the UI shows what the tick did; a
tick that fails after its retries fails the run. Old runs are deleted by the
cleaner. Its timeout comes in as the input, set by `af beads start` from
`[beads_poller]`.
"""

from datetime import timedelta

from pydantic import BaseModel
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporal_agentic_factory.watchers.beads.models import PollSummary
    from temporal_agentic_factory.watchers.beads.tick import BeadsPollActivity


class PollConfig(BaseModel):
    """One run's timeout, from `[beads_poller]` in the schedule's action."""

    tick_timeout_sec: int


@workflow.defn(name="beads_poll")
class BeadsPollWorkflow:
    """One tick; its summary is the result."""

    @workflow.run
    async def run(self, config: PollConfig) -> PollSummary:
        """One reconcile-and-spawn pass; a failure after its retries fails the run."""
        return await workflow.execute_activity_method(
            BeadsPollActivity.poll,
            start_to_close_timeout=timedelta(seconds=config.tick_timeout_sec),
            retry_policy=RetryPolicy(maximum_attempts=2),
            summary="beads tick",
        )
