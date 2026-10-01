from typing import Annotated, Any

import typer
from temporalio.client import WorkflowHandle

from distill.contract import DistillRequest
from temporal_agentic_factory.cli.admission import refuse_when_full
from temporal_agentic_factory.cli.errors import run_coro
from temporal_agentic_factory.cli.ids import new_id
from temporal_agentic_factory.client import awaited, connect
from temporal_agentic_factory.distill.workflow import DistilledEntry, DistillWorkflow, _job
from temporal_agentic_factory.job import search_attributes
from temporal_agentic_factory.options import absolute, given, source_url
from temporal_agentic_factory.settings.load import settings


def distill(
    url: Annotated[str, typer.Argument(help="http(s) URL, or a local .pdf/.md/.txt path")],
    topic: Annotated[str, typer.Option(help="snake_case research topic")] = "",
    chunk_chars: Annotated[int | None, typer.Option(help="target characters per chunk")] = None,
    research_target: Annotated[str, typer.Option(help="free text as Research-Target line")] = "",
    target_dir: Annotated[str, typer.Option(help="folder the entry is written into as is")] = "",
    detach: Annotated[bool, typer.Option("--detach", help="submit without waiting")] = False,
    workflow_id: Annotated[str | None, typer.Option(help="workflow id to start with")] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="start even past [limits] max_concurrent_jobs"),
    ] = False,
) -> None:
    """Submit one source; wait and print the entry folder, or just its id.
    Refused at the global concurrency cap unless --force."""
    if not force:
        refuse_when_full()
    request = DistillRequest(
        url=source_url(url),
        topic=topic,
        research_target=research_target,
        target_dir=absolute(target_dir) if target_dir else "",
        **given({"chunk_chars": chunk_chars}),
    )
    wid = new_id("distill", workflow_id)
    if detach:
        typer.echo(run_coro(_submitted_id(request, wid)))
    else:
        typer.echo(run_coro(_distilled_entry(request, wid)).model_dump_json(indent=2))


async def _submitted_id(request: DistillRequest, wid: str) -> str:
    """Workflow started but not waited for."""
    handle = await _started(request, wid)
    typer.echo(f"started {handle.id}", err=True)
    return handle.id


async def _distilled_entry(request: DistillRequest, wid: str) -> DistilledEntry:
    """Workflow started and waited for."""
    return await awaited(await _started(request, wid))


async def _started(request: DistillRequest, wid: str) -> WorkflowHandle[Any, DistilledEntry]:
    """Handle for the distill workflow with the run's search attributes."""
    return await (await connect()).start_workflow(
        DistillWorkflow.run,
        request,
        id=wid,
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(_job("", "")),
        static_summary=request.url,
    )
