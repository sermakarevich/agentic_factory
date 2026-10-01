import uuid

from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from temporal_agentic_factory.cleaner.rules import CleanSummary, TypeCleaned
from temporal_agentic_factory.cleaner.workflow import CleanConfig, CleanerWorkflow
from temporal_agentic_factory.settings.model import CleanRule

RULES = [CleanRule(workflow_type="beads_poll", keep_completed=1, keep_failed=3)]


async def test_a_run_cleans_with_its_rules_and_returns_the_summary() -> None:
    seen: list[list[CleanRule]] = []

    @activity.defn(name="clean_history")
    async def clean_history(rules: list[CleanRule]) -> CleanSummary:
        seen.append(rules)
        return CleanSummary(types=[TypeCleaned(workflow_type="beads_poll", completed=4)])

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        queue = f"test-{uuid.uuid4()}"
        async with Worker(
            env.client, task_queue=queue, workflows=[CleanerWorkflow], activities=[clean_history]
        ):
            summary = await env.client.execute_workflow(
                CleanerWorkflow.run,
                CleanConfig(rules=RULES, timeout_sec=30),
                id=f"cleaner-{uuid.uuid4()}",
                task_queue=queue,
            )
    assert seen == [RULES]
    assert summary.types == [TypeCleaned(workflow_type="beads_poll", completed=4)]
