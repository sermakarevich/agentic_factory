from temporalio import activity

from agentic_factory.failure import JobFailed
from agentic_factory.observe.log import LogObserver
from agentic_factory.step import engine as steps
from agentic_factory.step.contract import Step, StepResult
from temporal_agentic_factory.failure import to_application_error


@activity.defn
async def execute_step(step: Step) -> StepResult:
    """One llm step. Short, no heartbeat; Temporal retries it as a whole."""
    try:
        return await steps.run(step, LogObserver())
    except JobFailed as failure:
        raise to_application_error(failure) from failure
