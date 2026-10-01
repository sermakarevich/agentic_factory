"""The `af beads` commands on the database itself: init it, add a bead, list,
show and close beads."""

from pathlib import Path
from typing import Annotated

import typer

from temporal_agentic_factory.cli.beads.opened import beads_failures, configured, opened
from temporal_agentic_factory.cli.errors import fail
from temporal_agentic_factory.cli.providers import refuse_unconfigured
from temporal_agentic_factory.settings.load import settings

JsonOption = Annotated[bool, typer.Option("--json", help="bd's JSON instead of text")]


def init() -> None:
    """Create the beads database af owns at `[beads].home`; a second run changes nothing."""
    client = configured()
    with beads_failures():
        created = client.init()
    typer.echo(f"{'created' if created else 'already initialised'}: {client.home}", err=True)
    typer.echo(str(client.home))


def add(
    title: Annotated[str, typer.Argument(help="what the coder is asked, in one line")],
    cwd: Annotated[
        Path,
        typer.Option(
            exists=True, file_okay=False, resolve_path=True, help="the folder the coder works in"
        ),
    ],
    provider: Annotated[str, typer.Option(help="the coder: a configured [providers.<name>]")],
    model: Annotated[str, typer.Option(help="its model; empty = the provider's default")] = "",
    priority: Annotated[
        int | None, typer.Option(min=0, max=4, help="0 highest, 4 lowest; empty = settings")
    ] = None,
    body: Annotated[str | None, typer.Option(help="the bead's description")] = None,
    body_file: Annotated[
        Path | None,
        typer.Option(exists=True, dir_okay=False, help="a file holding the description"),
    ] = None,
) -> None:
    """Add an open bead routed to a provider and a workdir; prints its id."""
    refuse_unconfigured(provider)
    description = _description(body, body_file)
    client = opened()
    with beads_failures():
        bead_id = client.create(
            title,
            description,
            settings.beads.default_priority if priority is None else priority,
            provider,
            str(cwd),
            model,
        )
    typer.echo(bead_id)


def _description(body: str | None, body_file: Path | None) -> str:
    """The description from --body or --body-file; both is an error, neither is ""."""
    if body is not None and body_file is not None:
        fail("give --body or --body-file, not both")
    if body_file is not None:
        return body_file.read_text()
    return body or ""


def list_beads(
    status: Annotated[
        str | None, typer.Option(help="open, in_progress, blocked, deferred, closed")
    ] = None,
    limit: Annotated[int | None, typer.Option(help="most beads shown; empty = bd's own")] = None,
    as_json: JsonOption = False,
) -> None:
    """List beads, as `bd list` prints them."""
    args = ["list"]
    args += ["--status", status] if status else []
    args += ["--limit", str(limit)] if limit is not None else []
    _printed(args, as_json)


def show(
    bead_id: Annotated[str, typer.Argument(help="the bead id, e.g. af-1x2")],
    as_json: JsonOption = False,
) -> None:
    """Show one bead, as `bd show` prints it."""
    _printed(["show", bead_id], as_json)


def close(
    bead_id: Annotated[str, typer.Argument(help="the bead id, e.g. af-1x2")],
    reason: Annotated[str, typer.Option(help="why it is closed")] = "",
) -> None:
    """Close one bead by hand."""
    _printed(["close", bead_id, *(["--reason", reason] if reason else [])], as_json=False)


def _printed(args: list[str], as_json: bool) -> None:
    """`bd <args>` (with --json when asked) printed as it comes."""
    client = opened()
    with beads_failures():
        text = client.output([*args, "--json"] if as_json else args)
    typer.echo(text, nl=False)
