"""The cleaner: one clean of every rule; the `cleaner` Schedule starts it.

The clean's summary is the run's result, so the UI shows what was deleted.
The rules and the timeout come in as the input, set by `af cleaner start`
from `[cleaner]`, so a settings change takes `af cleaner restart`.
"""

from datetime import timedelta

from pydantic import BaseModel
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporal_agentic_factory.cleaner.clean import clean_history
    from temporal_agentic_factory.cleaner.rules import CleanSummary
    from temporal_agentic_factory.settings.model import CleanRule


class CleanConfig(BaseModel):
    """One run's rules and timeout, from `[cleaner]` in the schedule's action."""

    rules: list[CleanRule]
    timeout_sec: int


@workflow.defn(name="cleaner")
class CleanerWorkflow:
    """One clean; its summary is the result."""

    @workflow.run
    async def run(self, config: CleanConfig) -> CleanSummary:
        """Every rule applied once; the activity is best effort, the next run catches up."""
        return await workflow.execute_activity(
            clean_history,
            config.rules,
            start_to_close_timeout=timedelta(seconds=config.timeout_sec),
            retry_policy=RetryPolicy(maximum_attempts=1),
            summary="clean history",
        )
