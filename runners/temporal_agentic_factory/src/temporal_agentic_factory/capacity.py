"""The global job cap: free coder slots vs `[limits] max_concurrent_jobs`.

The cap covers every spawner (the beads poller, `af run`, `af distill`,
`af research`): coder subscriptions allow only so many live runs per hour.
Only workflow types that run a coder themselves are counted (`job`,
`job_with_structured_output`); distill and research only orchestrate, and
their coder work runs as those child workflows on the same queue.

It is a soft admission check, not a lock: Temporal's visibility counts lag
by a second or so, and two submits at once can both see the same free slot.
The hard per-machine limit stays `[runner] max_concurrent_activities`.
"""

from temporalio import workflow
from temporalio.client import Client

from temporal_agentic_factory.job.workflow import JobWorkflow
from temporal_agentic_factory.structured_output.workflow import JobWithStructuredOutputWorkflow

CODER_WORKFLOWS = (JobWorkflow, JobWithStructuredOutputWorkflow)


async def free_slots(client: Client, cap: int, task_queue: str) -> int | None:
    """Coder jobs that may still start on the queue; None when cap is 0 (no cap)."""
    if cap == 0:
        return None
    return max(cap - await running_coder_jobs(client, task_queue), 0)


async def running_coder_jobs(client: Client, task_queue: str) -> int:
    """Running workflows on the queue of a type that runs a coder itself."""
    counted = await client.count_workflows(_running_query(task_queue))
    return counted.count


def _running_query(task_queue: str) -> str:
    """The visibility query for running coder workflows on one queue."""
    types = ", ".join(f"'{_type_name(flow)}'" for flow in CODER_WORKFLOWS)
    return (
        f"WorkflowType IN ({types}) AND ExecutionStatus = 'Running' AND TaskQueue = '{task_queue}'"
    )


def _type_name(flow: type) -> str:
    """The name the workflow class is registered under (its `@workflow.defn`)."""
    name = workflow._Definition.must_from_class(flow).name
    if name is None:
        raise TypeError(f"{flow.__name__} is a dynamic workflow: it has no type name")
    return name
