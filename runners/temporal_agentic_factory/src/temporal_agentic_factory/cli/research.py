"""The `af run research` command: one focus question submitted to Temporal, waited for
by default."""

from typing import Annotated

import typer
from research.contract import ResearchedTopic, ResearchRequest

from temporal_agentic_factory.cli.errors import run_coro
from temporal_agentic_factory.cli.ids import new_id
from temporal_agentic_factory.cli.options import given, tool_list
from temporal_agentic_factory.cli.providers import refuse_unconfigured
from temporal_agentic_factory.client import awaited, connect
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.workflows.job import search_attributes
from temporal_agentic_factory.workflows.research.workflow import ResearchWorkflow, research_job


def research(
    topics: Annotated[str, typer.Argument(help="comma-separated sub-topic slugs")],
    focus: Annotated[str, typer.Option(help="what question the research must answer, for whom")],
    target: Annotated[
        str, typer.Option(help="folder slug under research_topics/<topic>/research/")
    ],
    topic: Annotated[str, typer.Option(help="snake_case research topic folder; must exist")],
    n_sources: Annotated[
        int | None, typer.Option(help="how many sources the shortlist holds")
    ] = None,
    lenses: Annotated[str | None, typer.Option(help="comma-separated audiences")] = None,
    date_from: Annotated[str | None, typer.Option(help="ignore sources older than this")] = None,
    kinds: Annotated[str | None, typer.Option(help="comma-separated kinds")] = None,
    detach: Annotated[
        bool, typer.Option("--detach", help="submit and print the workflow id without waiting")
    ] = False,
    workflow_id: Annotated[
        str | None,
        typer.Option(
            help="workflow id to start with; reusing one is idempotent. Empty = generated"
        ),
    ] = None,
) -> None:
    """Submit one focus question to Temporal. Waits and prints where the run
    landed and what it made as JSON, or with --detach prints the workflow id.
    Options left out keep the settings defaults. Refused when a
    `[research_workflow]` provider has no `[providers.<name>]` table."""
    request = ResearchRequest(
        topics=tool_list(topics) or [],
        focus=focus,
        target=target,
        topic=topic,
        **given(
            {
                "n_sources": n_sources,
                "lenses": tool_list(lenses),
                "date_from": date_from,
                "kinds": tool_list(kinds),
            }
        ),
    )
    cfg = settings.research_workflow
    refuse_unconfigured(cfg.provider, cfg.planning_provider)
    result = run_coro(_started(request, workflow_id, detach))
    typer.echo(result if isinstance(result, str) else result.model_dump_json(indent=2))


async def _started(
    request: ResearchRequest, workflow_id: str | None, detach: bool
) -> str | ResearchedTopic:
    """The research workflow started; its id when detached, else what it
    made once it is done. The UI columns show the coder every research job
    runs on, the name is `<topic>/<target>`; the run's summary is the focus
    question."""
    name = f"{request.topic}/{request.target}"
    client = await connect()
    handle = await client.start_workflow(
        ResearchWorkflow.run,
        request,
        id=new_id("research", name, workflow_id),
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(research_job("", ""), name),
        static_summary=request.focus,
    )
    if detach:
        typer.echo(f"started {handle.id}", err=True)
        return handle.id
    return await awaited(handle)
