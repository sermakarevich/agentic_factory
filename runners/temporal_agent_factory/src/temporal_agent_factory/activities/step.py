from temporalio import activity

from agent_factory.failure import JobFailed
from agent_factory.observe.log import LogObserver
from agent_factory.step import engine as steps
from agent_factory.step.contract import Step, StepResult
from temporal_agent_factory.failure import to_application_error


@activity.defn
async def execute_step(step: Step) -> StepResult:
    """One llm step. Short, no heartbeat; Temporal retries it as a whole."""
    try:
        return await steps.run(step, LogObserver())
    except JobFailed as failure:
        raise to_application_error(failure) from failure
