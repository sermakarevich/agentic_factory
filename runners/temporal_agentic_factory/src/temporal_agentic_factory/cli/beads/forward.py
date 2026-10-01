"""The rest of `bd`, reached through af: `af beads bd <args...>` runs
`bd <args...>` in the beads home, and any `af beads <cmd>` af does not define
itself is forwarded the same way. af's own commands win: `af beads bd status`
reaches bd's status."""

import typer
from typer import _click
from typer.core import TyperCommand, TyperGroup

from temporal_agentic_factory.cli.beads.opened import beads_failures, opened
from temporal_agentic_factory.watchers.beads.shell import forward_bd

BD = "bd"


class VerbatimCommand(TyperCommand):
    """A command whose every argument, `--help` and `--` included, is left for
    it in `ctx.args` untouched."""

    def parse_args(self, ctx: _click.Context, args: list[str]) -> list[str]:
        ctx.args = list(args)
        return []


class ForwardingGroup(TyperGroup):
    """A group that hands a command it does not define, with its arguments, to `bd`."""

    def resolve_command(
        self, ctx: _click.Context, args: list[str]
    ) -> tuple[str | None, _click.Command | None, list[str]]:
        if args and self.get_command(ctx, args[0]) is None:
            return BD, self.get_command(ctx, BD), args
        return super().resolve_command(ctx, args)


def bd(ctx: typer.Context) -> None:
    """Run `bd <args...>` in the beads home; its output and exit code as they come."""
    client = opened()
    with beads_failures():
        code = forward_bd(ctx.args, client.home)
    raise typer.Exit(code)
