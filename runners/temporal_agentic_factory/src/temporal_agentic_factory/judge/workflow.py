"""For any workflow that branches on a judge's answer: the judge activity
with its timeout and retry policy. No workflow of its own; a judgment is
one step inside a workflow, never the whole of one."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from agentic_factory.step.judge.contract import Judgment, JudgmentResult
    from temporal_agentic_factory.judge.activity import judge
    from temporal_agentic_factory.settings.load import settings


async def run_judgment(judgment: Judgment) -> JudgmentResult:
    """The judge activity, given as long as the judgment's own timeout plus
    a margin, with the judge activity's retry policy; the UI shows the
    names of the questions asked."""
    cfg = settings.judge_activity
    return await workflow.execute_activity(
        judge,
        judgment,
        start_to_close_timeout=timedelta(seconds=judgment.timeout_sec + cfg.close_margin_sec),
        retry_policy=RetryPolicy(maximum_attempts=cfg.max_attempts),
        summary=", ".join(judgment.questions),
    )
