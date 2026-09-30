from temporalio import activity

from agentic_factory.callbacks.log import LogCallback
from agentic_factory.failure import JobFailed
from agentic_factory.step import engine as steps
from agentic_factory.step.contract import Step, StepResult
from agentic_factory.step.providers.catalog import client_for
from temporal_agentic_factory.activities.failure import to_application_error


@activity.defn
async def execute_step(step: Step) -> StepResult:
    """One llm step. Short, no heartbeat; Temporal retries it as a whole."""
    try:
        return await steps.run(step, LogCallback(), client_for(step.provider))
    except JobFailed as failure:
        raise to_application_error(failure) from failure
