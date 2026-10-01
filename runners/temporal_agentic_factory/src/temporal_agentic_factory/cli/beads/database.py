"""The `af beads` commands on the database itself: init it, list, show and
close beads."""

from typing import Annotated

import typer

from temporal_agentic_factory.cli.beads.opened import beads_failures, configured, opened

JsonOption = Annotated[bool, typer.Option("--json", help="bd's JSON instead of text")]


def init() -> None:
    """Create the beads database af owns at `[beads].home`; a second run changes nothing."""
    client = configured()
    with beads_failures():
        created = client.init()
    typer.echo(f"{'created' if created else 'already initialised'}: {client.home}", err=True)
    typer.echo(str(client.home))


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
