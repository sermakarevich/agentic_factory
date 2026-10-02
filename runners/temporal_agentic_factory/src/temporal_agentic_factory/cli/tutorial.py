"""The `af run tutorial` command: one topic submitted to Temporal, waited for by default."""

from typing import Annotated

import typer
from tutorial.contract import Coder, TutorialOutcome, TutorialRequest
from tutorial.settings.load import settings as tutorial_settings
from tutorial.settings.model import CoderSettings

from temporal_agentic_factory.cli.errors import run_coro
from temporal_agentic_factory.cli.ids import new_id
from temporal_agentic_factory.cli.options import absolute, given, tool_list
from temporal_agentic_factory.cli.providers import refuse_unconfigured
from temporal_agentic_factory.client import awaited, connect
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.workflows.job import search_attributes
from temporal_agentic_factory.workflows.tutorial.workflow import TutorialWorkflow, role_job


def tutorial(
    topic: Annotated[str, typer.Argument(help="what the tutorial teaches")],
    name: Annotated[str | None, typer.Option(help="folder under the root; empty = picked")] = None,
    root: Annotated[
        str | None,
        typer.Option(help="tutorials folder for this run; default: knowledge/tutorials"),
    ] = None,
    formats: Annotated[str | None, typer.Option(help="comma-separated: md, ipynb")] = None,
    level: Annotated[str | None, typer.Option(help="beginner, intermediate or advanced")] = None,
    review_rounds: Annotated[
        int | None, typer.Option(help="rewrite rounds a failing chapter gets")
    ] = None,
    designer_provider: Annotated[str | None, typer.Option(help="designer's provider")] = None,
    designer_model: Annotated[str | None, typer.Option(help="designer's model")] = None,
    writer_provider: Annotated[str | None, typer.Option(help="writers' provider")] = None,
    writer_model: Annotated[str | None, typer.Option(help="writers' model")] = None,
    reviewer_provider: Annotated[str | None, typer.Option(help="reviewers' provider")] = None,
    reviewer_model: Annotated[str | None, typer.Option(help="reviewers' model")] = None,
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
    """Submit one topic to Temporal, written up as a tutorial in
    <root>/<name>/ (root: knowledge/tutorials in the vault unless --root).
    Waits and prints how each chapter ended as JSON, or with --detach
    prints the workflow id. Options left out keep the settings defaults.
    Refused when a role's provider has no providers table in settings."""
    request = TutorialRequest(
        topic=topic,
        **given(
            {
                "name": name,
                "root": absolute(root) if root else None,
                "formats": tool_list(formats),
                "level": level,
                "review_rounds": review_rounds,
            }
        ),
        designer=coder(designer_provider, designer_model, tutorial_settings.designer),
        writer=coder(writer_provider, writer_model, tutorial_settings.writer),
        reviewer=coder(reviewer_provider, reviewer_model, tutorial_settings.reviewer),
    )
    refuse_unconfigured(
        request.designer.provider, request.writer.provider, request.reviewer.provider
    )
    result = run_coro(_started(request, workflow_id, detach))
    typer.echo(result if isinstance(result, str) else result.model_dump_json(indent=2))


def coder(provider: str | None, model: str | None, defaults: CoderSettings) -> Coder:
    """The role's coder: the options given, the settings for the rest. A new
    provider without a model runs on the harness's default one."""
    if provider is None:
        return Coder(provider=defaults.provider, model=model or defaults.model)
    return Coder(provider=provider, model=model or "")


async def _started(
    request: TutorialRequest, workflow_id: str | None, detach: bool
) -> str | TutorialOutcome:
    """The tutorial workflow started; its id when detached, else its outcome
    once it is done. The UI columns show the designer's coder, the name is the
    folder (or the topic until the naming job picks one); the run's summary
    is the topic."""
    label = request.name or request.topic
    job = role_job("design", "", request.designer, tutorial_settings.designer)
    client = await connect()
    handle = await client.start_workflow(
        TutorialWorkflow.run,
        request,
        id=new_id("tutorial", label, workflow_id),
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(job, label),
        static_summary=request.topic,
    )
    if detach:
        typer.echo(f"started {handle.id}", err=True)
        return handle.id
    return await awaited(handle)
