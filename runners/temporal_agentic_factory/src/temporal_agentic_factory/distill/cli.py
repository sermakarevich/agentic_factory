"""The `distill` command: one source turned into a knowledge-base entry."""

import asyncio
from typing import Annotated
from uuid import uuid4

import typer

from distill.contract import DistillRequest
from temporal_agentic_factory.client import awaited, connect
from temporal_agentic_factory.distill.workflow import (
    DistilledEntry,
    DistillWorkflow,
    distill_job,
)
from temporal_agentic_factory.job import search_attributes
from temporal_agentic_factory.options import absolute, given, source_url
from temporal_agentic_factory.settings.load import settings


def distill(
    url: Annotated[str, typer.Argument(help="http(s) URL, or a local .pdf/.md/.txt path")],
    topic: Annotated[
        str, typer.Option(help="snake_case research topic to file the entry under")
    ] = "",
    chunk_chars: Annotated[int | None, typer.Option(help="target characters per chunk")] = None,
    research_target: Annotated[
        str, typer.Option(help="free text kept as the entry's Research-Target line")
    ] = "",
    target_dir: Annotated[
        str, typer.Option(help="folder the entry is written into as is (not with --topic)")
    ] = "",
) -> None:
    """Turn one source into a knowledge-base entry on Temporal and wait for
    it. Prints the entry's folder, plan and fetched source as JSON."""
    request = DistillRequest(
        url=source_url(url),
        topic=topic,
        research_target=research_target,
        target_dir=absolute(target_dir) if target_dir else "",
        **given({"chunk_chars": chunk_chars}),
    )
    typer.echo(asyncio.run(_distilled_entry(request)).model_dump_json(indent=2))


async def _distilled_entry(request: DistillRequest) -> DistilledEntry:
    """The distill workflow started and waited for. The UI columns show
    the coder every distill job runs on, from the job the prompts go into;
    the run's summary is the source."""
    client = await connect()
    handle = await client.start_workflow(
        DistillWorkflow.run,
        request,
        id=f"distill-{uuid4().hex[: settings.cli.job_id_chars]}",
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(distill_job("", "")),
        static_summary=request.url,
    )
    return await awaited(handle)
