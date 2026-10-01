"""The clean activity: for each rule, list the closed runs of its type, pick the
old ones, delete each by its run id.

Best effort: a failed listing or delete is logged and counted, never raised.
Only the rule's type is touched, by the query and again by the selection.
"""

import logging

from temporalio import activity
from temporalio.api.common.v1 import WorkflowExecution as ExecutionRef
from temporalio.api.workflowservice.v1 import DeleteWorkflowExecutionRequest
from temporalio.client import Client, WorkflowExecution

from temporal_agentic_factory.cleaner.rules import CleanSummary, TypeCleaned, runs_to_delete
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.settings.model import CleanRule

logger = logging.getLogger(__name__)


@activity.defn
async def clean_history(rules: list[CleanRule]) -> CleanSummary:
    """Every rule applied on the configured server; what was deleted."""
    return await cleaned(await connect(), settings.temporal.namespace, rules)


async def cleaned(client: Client, namespace: str, rules: list[CleanRule]) -> CleanSummary:
    """Every rule applied in turn; what each deleted."""
    return CleanSummary(types=[await _rule_applied(client, namespace, rule) for rule in rules])


def closed_runs_query(workflow_type: str) -> str:
    """The visibility query for the closed runs of one type."""
    return f"WorkflowType = '{workflow_type}' AND ExecutionStatus != 'Running'"


async def _rule_applied(client: Client, namespace: str, rule: CleanRule) -> TypeCleaned:
    """The old runs of one type deleted; a failed listing is one error and nothing deleted."""
    try:
        runs = [run async for run in client.list_workflows(closed_runs_query(rule.workflow_type))]
    except Exception as error:
        logger.warning("listing %s runs failed: %s", rule.workflow_type, error)
        return TypeCleaned(workflow_type=rule.workflow_type, errors=1)
    selected = runs_to_delete(runs, rule)
    completed = [await _deleted(client, namespace, run) for run in selected.completed]
    failed = [await _deleted(client, namespace, run) for run in selected.failed]
    return TypeCleaned(
        workflow_type=rule.workflow_type,
        completed=completed.count(True),
        failed=failed.count(True),
        errors=(completed + failed).count(False),
    )


async def _deleted(client: Client, namespace: str, run: WorkflowExecution) -> bool:
    """One run (by its run id, never the current one by workflow id) deleted; False on failure."""
    try:
        await client.workflow_service.delete_workflow_execution(
            DeleteWorkflowExecutionRequest(
                namespace=namespace,
                workflow_execution=ExecutionRef(workflow_id=run.id, run_id=run.run_id),
            )
        )
    except Exception as error:
        logger.warning(
            "deleting %s run %s/%s failed: %s", run.workflow_type, run.id, run.run_id, error
        )
        return False
    return True
