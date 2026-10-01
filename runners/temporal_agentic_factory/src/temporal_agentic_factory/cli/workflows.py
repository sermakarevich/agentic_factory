"""The `af` workflow commands: list, status, result, cancel, terminate.

Submit commands live beside this module, one per subject (`job.py`, `distill.py`);
everything here only operates on workflows that already exist.
"""

import json
from datetime import datetime
from typing import Annotated, Any

import typer
from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest
from temporalio.client import Client, WorkflowExecution, WorkflowHandle

from agentic_factory.job.outcome import JobOutcome
from temporal_agentic_factory.cli.errors import (
    STATUSES,
    WORKFLOW_TYPES,
    normalize_status,
    normalize_workflow_type,
    run_coro,
)
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.workflows.distill.workflow import DistilledEntry
from temporal_agentic_factory.workflows.job.coder_queue import coder_queue
from temporal_agentic_factory.workflows.job.search_attributes import NAME
from temporal_agentic_factory.workflows.structured_output.workflow import JobWithStructuredOutput

RESULT_TYPES: dict[str, Any] = {
    "job": JobOutcome,
    "job_with_structured_output": JobWithStructuredOutput,
    "distill": DistilledEntry,
}


def _result_type_for(workflow_type: str) -> Any | None:
    return RESULT_TYPES.get(workflow_type)


async def _handle(
    client: Client, workflow_id: str, run_id: str | None = None
) -> WorkflowHandle[Any, Any]:
    return client.get_workflow_handle(workflow_id, run_id=run_id)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _status_name(status: Any) -> str:
    name = getattr(status, "name", None)
    return str(name or status)


async def _describe_dict(
    client: Client, workflow_id: str, run_id: str | None = None
) -> dict[str, Any]:
    handle = await _handle(client, workflow_id, run_id)
    desc = await handle.describe()
    search = {pair.key.name: pair.value for pair in desc.typed_search_attributes}
    return {
        "workflow_id": desc.id,
        "run_id": desc.run_id,
        "workflow_type": desc.workflow_type,
        "status": _status_name(desc.status),
        "task_queue": desc.task_queue,
        "start_time": _iso(desc.start_time),
        "execution_time": _iso(desc.execution_time),
        "close_time": _iso(desc.close_time),
        "history_length": desc.history_length,
        "parent_id": desc.parent_id,
        "search_attributes": search,
        "static_summary": await desc.static_summary(),
        "static_details": await desc.static_details(),
    }


def _print_status(info: dict[str, Any], as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(info, indent=2))
        return
    for key in (
        "workflow_id",
        "run_id",
        "workflow_type",
        "status",
        "task_queue",
        "start_time",
        "close_time",
        "history_length",
        "static_summary",
        "static_details",
    ):
        typer.echo(f"{key}: {info.get(key)}")
    typer.echo(f"search_attributes: {json.dumps(info.get('search_attributes', {}))}")


def status(
    workflow_id: Annotated[str, typer.Argument(help="workflow id, e.g. job-9f3c2a1b")],
    run_id: Annotated[
        str | None, typer.Option(help="one run of the workflow; empty = current")
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="print the description as JSON")
    ] = False,
) -> None:
    """Show one workflow: type, status, times, summary and search attributes."""
    info = run_coro(_describe_dict_async(workflow_id, run_id))
    _print_status(info, json_output)


async def _describe_dict_async(workflow_id: str, run_id: str | None) -> dict[str, Any]:
    return await _describe_dict(await connect(), workflow_id, run_id)


def result(
    workflow_id: Annotated[str, typer.Argument(help="workflow id to fetch the result of")],
    run_id: Annotated[
        str | None, typer.Option(help="one run of the workflow; empty = current")
    ] = None,
) -> None:
    """Print a finished workflow's result as JSON. Waits when it still runs."""
    typer.echo(run_coro(_result_json(workflow_id, run_id)))


async def _result_json(workflow_id: str, run_id: str | None) -> str:
    client = await connect()
    info = await _describe_dict(client, workflow_id, run_id)
    workflow_type = info["workflow_type"] or ""
    handle = client.get_workflow_handle(
        workflow_id, run_id=run_id, result_type=_result_type_for(workflow_type)
    )
    value: Any = await handle.result()
    if hasattr(value, "model_dump_json"):
        dumped: str = value.model_dump_json(indent=2)
        return dumped
    return json.dumps(value, indent=2, default=str)


def list_workflows(
    limit: Annotated[int, typer.Option(help="at most this many workflows")] = 20,
    query: Annotated[
        str | None,
        typer.Option(help="Temporal visibility query, e.g. \"ExecutionStatus = 'Running'\""),
    ] = None,
    status_filter: Annotated[
        str | None,
        typer.Option("--status", help=f"any of {', '.join(STATUSES)}, any case"),
    ] = None,
    workflow_type: Annotated[
        str | None, typer.Option("--type", help=f"any of {', '.join(WORKFLOW_TYPES)}")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="one JSON object per line")] = False,
) -> None:
    """List workflows, newest first. Filters narrow the server-side query."""
    for line in run_coro(_listed(limit, query, status_filter, workflow_type, json_output)):
        typer.echo(line)


async def _listed(
    limit: int,
    query: str | None,
    status_filter: str | None,
    workflow_type: str | None,
    as_json: bool,
) -> list[str]:
    client = await connect()
    parts = [query] if query else []
    if status_filter:
        parts.append(f"ExecutionStatus = '{normalize_status(status_filter)}'")
    if workflow_type:
        parts.append(f"WorkflowType = '{normalize_workflow_type(workflow_type)}'")
    combined = " AND ".join(f"({p})" for p in parts) or None
    lines: list[str] = []
    count = 0
    async for execution in client.list_workflows(combined, limit=limit):
        count += 1
        lines.append(_execution_line(execution, as_json))
        if count >= limit:
            break
    return lines


def _execution_line(execution: WorkflowExecution, as_json: bool) -> str:
    if as_json:
        return json.dumps(
            {
                "workflow_id": execution.id,
                "run_id": execution.run_id,
                "workflow_type": execution.workflow_type,
                "name": execution.typed_search_attributes.get(NAME),
                "status": _status_name(execution.status),
                "start_time": _iso(execution.start_time),
                "execution_time": _iso(execution.execution_time),
                "close_time": _iso(execution.close_time),
                "history_length": execution.history_length,
            },
            default=str,
        )
    status = _status_name(execution.status)
    started = _iso(execution.start_time)
    workflow_type = execution.workflow_type or "?"
    name = execution.typed_search_attributes.get(NAME) or "-"
    return f"{execution.id} {workflow_type} {status} name={name} started={started}"


def cancel(
    workflow_id: Annotated[str, typer.Argument(help="workflow id to cancel")],
    run_id: Annotated[
        str | None, typer.Option(help="one run of the workflow; empty = current")
    ] = None,
    reason: Annotated[str, typer.Option(help="why it is cancelled, recorded in history")] = "",
) -> None:
    """Request cancellation of a running workflow. Activities get cancelled, not killed."""
    run_coro(_cancelled(workflow_id, run_id, reason))
    typer.echo(f"cancel requested: {workflow_id}", err=True)


async def _cancelled(workflow_id: str, run_id: str | None, reason: str) -> None:
    handle = await _handle(await connect(), workflow_id, run_id)
    await handle.cancel(reason=reason)


def terminate(
    workflow_id: Annotated[str, typer.Argument(help="workflow id to terminate")],
    run_id: Annotated[
        str | None, typer.Option(help="one run of the workflow; empty = current")
    ] = None,
    reason: Annotated[str, typer.Option(help="why it is terminated, recorded in history")] = "",
) -> None:
    """Terminate a workflow immediately, without waiting for activities."""
    run_coro(_terminated(workflow_id, run_id, reason))
    typer.echo(f"terminated: {workflow_id}", err=True)


async def _terminated(workflow_id: str, run_id: str | None, reason: str) -> None:
    handle = await _handle(await connect(), workflow_id, run_id)
    await handle.terminate(reason=reason or None)


def health() -> None:
    """Check the Temporal server answers: prints address, namespace, task
    queue, and which processes poll each provider's coder queue (none: start
    `af coders`)."""
    info = run_coro(_health_info())
    typer.echo(json.dumps(info, indent=2))


async def _health_info() -> dict[str, Any]:
    client = await connect()
    counted = await client.count_workflows(f"TaskQueue = '{settings.temporal.task_queue}'")
    return {
        "address": settings.temporal.address,
        "namespace": settings.temporal.namespace,
        "task_queue": settings.temporal.task_queue,
        "workflows_on_task_queue": counted.count,
        "coder_queue_pollers": {
            coder_queue(name): await _pollers(client, coder_queue(name))
            for name in settings.providers
        },
    }


async def _pollers(client: Client, task_queue: str) -> list[str]:
    """The identities of the processes that polled `task_queue` for activities lately."""
    described = await client.workflow_service.describe_task_queue(
        DescribeTaskQueueRequest(
            namespace=settings.temporal.namespace,
            task_queue=TaskQueue(name=task_queue),
            task_queue_type=TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY,
        )
    )
    return [poller.identity for poller in described.pollers]
