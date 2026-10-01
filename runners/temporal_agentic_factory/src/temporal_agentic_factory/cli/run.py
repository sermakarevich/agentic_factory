"""The `af run` typer group: one subcommand per workflow, registered here and
nowhere else, so a new workflow is one line."""

import typer
from typer import _click
from typer.core import TyperGroup

from temporal_agentic_factory.cli.autocode import autocode
from temporal_agentic_factory.cli.distill import distill
from temporal_agentic_factory.cli.errors import fail
from temporal_agentic_factory.cli.job import run
from temporal_agentic_factory.cli.research import research
from temporal_agentic_factory.cli.tutorial import tutorial

JOB_HINT = 'to run a job: af run job "<prompt>"'


class WorkflowGroup(TyperGroup):
    """A group that refuses a name it does not define by listing the ones it does;
    a first argument with a space in it is an old-style prompt and gets a hint."""

    def resolve_command(
        self, ctx: _click.Context, args: list[str]
    ) -> tuple[str | None, _click.Command | None, list[str]]:
        if args and not ctx.resilient_parsing and self.unknown(ctx, args[0]):
            fail(self.refusal(ctx, args[0]))
        return super().resolve_command(ctx, args)

    def unknown(self, ctx: _click.Context, name: str) -> bool:
        return not name.startswith("-") and self.get_command(ctx, name) is None

    def refusal(self, ctx: _click.Context, name: str) -> str:
        """The unknown name and the workflows to choose from, plus the job hint for a prompt."""
        message = f"unknown workflow {name!r}; choose from: {', '.join(self.list_commands(ctx))}"
        return f"{message}\n{JOB_HINT}" if " " in name.strip() else message


run_app = typer.Typer(
    cls=WorkflowGroup,
    no_args_is_help=True,
    help="Start a workflow: af run <workflow> <its arguments and options>.",
)

run_app.command(name="job", short_help="One coder job on a prompt.")(run)
run_app.command(name="research", short_help="A focus question into a folder of digests.")(research)
run_app.command(name="distill", short_help="One source into a knowledge-base entry.")(distill)
run_app.command(name="tutorial", short_help="A topic into tutorial chapters.")(tutorial)
run_app.command(name="autocode", short_help="A feature spec into tested, committed code.")(autocode)
