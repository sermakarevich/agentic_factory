"""The `af run autocode` command: one feature submitted to Temporal, waited for by default."""

import os
from typing import Annotated

import typer
from autocode.contract import Autocoded, AutocodeRequest
from autocode.run import Autocode

from temporal_agentic_factory.cli.errors import run_coro
from temporal_agentic_factory.cli.ids import new_id
from temporal_agentic_factory.cli.options import absolute
from temporal_agentic_factory.cli.providers import refuse_unconfigured
from temporal_agentic_factory.client import awaited, connect
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.workflows.autocode.workflow import AutocodeWorkflow, autocode_job
from temporal_agentic_factory.workflows.job import search_attributes


def autocode(
    repo: Annotated[str, typer.Option(help="the git repo to build the feature in; clean tree")],
    feature: Annotated[str, typer.Option(help="slug: branch autocode/<feature>, docs/<feature>/")],
    spec: Annotated[str, typer.Option(help="the spec: a file's path, or the text itself")],
    provider: Annotated[str | None, typer.Option(help="every job's provider")] = None,
    model: Annotated[
        str | None, typer.Option(help="every job's model but the review's; empty = settings")
    ] = None,
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
    """Submit one feature to Temporal, built from its spec on the branch
    autocode/<feature> of the repo, each stage committed there, never pushed.
    Waits and prints the branch, commits, findings, spend and gate as JSON,
    or with --detach prints the workflow id. Options left out keep the
    settings defaults. Refused when the provider has no providers table in
    settings."""
    request = AutocodeRequest(
        repo=absolute(repo), feature=feature, spec=spec_of(spec), **coder(provider, model)
    )
    refuse_unconfigured(request.provider)
    result = run_coro(_started(request, workflow_id, detach))
    typer.echo(result if isinstance(result, str) else result.model_dump_json(indent=2))


def spec_of(spec: str) -> str:
    """An existing file's path made absolute, since the runner's cwd is not
    ours; anything else is the spec's text."""
    return absolute(spec) if os.path.isfile(os.path.expanduser(spec)) else spec


def coder(provider: str | None, model: str | None) -> dict[str, str]:
    """The request's coder fields given; the review keeps its own model on
    the settings' provider. A new provider runs every job, the review's
    too, on the model given, else on the harness's default one."""
    if provider is None:
        return {"model": model} if model else {}
    return {"provider": provider, "model": model or "", "review_model": model or ""}


async def _started(
    request: AutocodeRequest, workflow_id: str | None, detach: bool
) -> str | Autocoded:
    """The autocode workflow started; its id when detached, else its outcome
    once it is done. The UI columns show the run's coder, the name is the
    feature; the run's summary is the repo and the feature."""
    job = autocode_job(Autocode(request=request), "requirements", "")
    client = await connect()
    handle = await client.start_workflow(
        AutocodeWorkflow.run,
        request,
        id=new_id("autocode", request.feature, workflow_id),
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(job, request.feature),
        static_summary=f"{request.feature} in {request.repo}",
    )
    if detach:
        typer.echo(f"started {handle.id}", err=True)
        return handle.id
    return await awaited(handle)
