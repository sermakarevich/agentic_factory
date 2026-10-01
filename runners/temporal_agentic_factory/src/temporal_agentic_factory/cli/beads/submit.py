"""The `af beads` commands that submit work: add a bead with its job options and
its place in a chain, change a waiting bead's job options, retry a blocked one."""

from pathlib import Path
from typing import Annotated

import typer

from temporal_agentic_factory.cli.beads.job_options import (
    ContextLimitOption,
    ModelOption,
    NameOption,
    ProviderOption,
    StallOption,
    StructuredOutputOption,
    TimeoutOption,
    ToolsOption,
    WorkdirOption,
    job_fields,
    valid_fields,
)
from temporal_agentic_factory.cli.beads.opened import beads_failures, opened
from temporal_agentic_factory.cli.errors import fail
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.markers import retried
from temporal_agentic_factory.watchers.beads.models import BeadOptions, Status

BeadIdArgument = Annotated[str, typer.Argument(help="the bead id, e.g. af-1x2")]
SETTLED = (Status.IN_PROGRESS, Status.CLOSED)  # a job runs or ran: its options are spent


def add(  # noqa: PLR0913 - one parameter per option, as `af run job` has them
    title: Annotated[str, typer.Argument(help="what the coder is asked, in one line")],
    provider: ProviderOption = None,
    model: ModelOption = None,
    name: NameOption = None,
    workdir: WorkdirOption = None,
    tools: ToolsOption = None,
    timeout_sec: TimeoutOption = None,
    stall_sec: StallOption = None,
    context_limit_tokens: ContextLimitOption = None,
    structured_output: StructuredOutputOption = None,
    priority: Annotated[
        int | None, typer.Option(min=0, max=4, help="0 highest, 4 lowest; empty = settings")
    ] = None,
    body: Annotated[str | None, typer.Option(help="the bead's description")] = None,
    body_file: Annotated[
        Path | None,
        typer.Option(exists=True, dir_okay=False, help="a file holding the description"),
    ] = None,
    after: Annotated[
        list[str] | None, typer.Option(help="a bead this one waits for; repeatable")
    ] = None,
    parent: Annotated[str, typer.Option(help="the epic this bead belongs to")] = "",
    label: Annotated[list[str] | None, typer.Option(help="a label; repeatable")] = None,
    bead_type: Annotated[
        str, typer.Option("--type", help="task, bug, feature, epic, ...; empty = bd's own")
    ] = "",
    bead_id: Annotated[str, typer.Option("--id", help="the id to give it; empty = bd's own")] = "",
) -> None:
    """Add an open bead: only the job options given go in its `af_job`; prints its id."""
    fields = job_fields(
        {
            "provider": provider,
            "model": model,
            "name": name,
            "workdir": workdir,
            "tools": tools,
            "timeout_sec": timeout_sec,
            "stall_sec": stall_sec,
            "context_limit_tokens": context_limit_tokens,
            "structured_output": structured_output,
        }
    )
    description = _description(body, body_file)
    options = BeadOptions(
        after=after or [], parent=parent, labels=label or [], type=bead_type, id=bead_id
    )
    client = opened()
    with beads_failures():
        created = client.create(
            title,
            description,
            settings.beads.default_priority if priority is None else priority,
            fields,
            options,
        )
    typer.echo(created)


def set_job(  # noqa: PLR0913 - one parameter per option, as `af run job` has them
    bead_id: BeadIdArgument,
    provider: ProviderOption = None,
    model: ModelOption = None,
    name: NameOption = None,
    workdir: WorkdirOption = None,
    tools: ToolsOption = None,
    timeout_sec: TimeoutOption = None,
    stall_sec: StallOption = None,
    context_limit_tokens: ContextLimitOption = None,
    structured_output: StructuredOutputOption = None,
) -> None:
    """Merge the job options given into a waiting bead's `af_job`; refused once
    its job runs or ran."""
    fields = job_fields(
        {
            "provider": provider,
            "model": model,
            "name": name,
            "workdir": workdir,
            "tools": tools,
            "timeout_sec": timeout_sec,
            "stall_sec": stall_sec,
            "context_limit_tokens": context_limit_tokens,
            "structured_output": structured_output,
        }
    )
    if not fields:
        fail("give at least one job option to set")
    client = opened()
    with beads_failures():
        bead = client.bead(bead_id)
    if bead.status in SETTLED:
        fail(f"{bead_id} is {bead.status}: its job options can no longer change")
    current = bead.job_fields if isinstance(bead.job_fields, dict) else {}
    merged = valid_fields(current | fields)
    with beads_failures():
        client.set_job_fields(bead_id, merged)
    typer.echo(bead_id)


def retry(
    bead_id: BeadIdArgument,
    reason: Annotated[str, typer.Option(help="why it is retried")] = "",
) -> None:
    """Reopen a blocked bead; the watcher runs it again under a new workflow id."""
    client = opened()
    with beads_failures():
        bead = client.bead(bead_id)
        if bead.status != Status.BLOCKED:
            fail(f"{bead_id} is {bead.status or 'of unknown status'}, not blocked")
        client.note(bead_id, retried(reason))  # before it is ready: ends the old marker
        client.unblock(bead_id)
    typer.echo(bead_id)


def _description(body: str | None, body_file: Path | None) -> str:
    """The description from --body or --body-file; both is an error, neither is ""."""
    if body is not None and body_file is not None:
        fail("give --body or --body-file, not both")
    if body_file is not None:
        return body_file.read_text()
    return body or ""
