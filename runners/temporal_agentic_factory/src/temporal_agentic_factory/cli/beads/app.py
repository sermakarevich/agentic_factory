"""The `af beads` typer group: every beads command registered on it."""

import typer

from temporal_agentic_factory.cli.beads import database, poller

beads_app = typer.Typer(
    no_args_is_help=True, help="Beads: submit beads to the database af owns, pull them as jobs."
)

beads_app.command(name="init")(database.init)
beads_app.command(name="add")(database.add)
beads_app.command(name="list")(database.list_beads)
beads_app.command(name="show")(database.show)
beads_app.command(name="close")(database.close)
beads_app.command(name="ready")(poller.ready)
beads_app.command(name="poll")(poller.poll)
beads_app.command(name="schedule")(poller.schedule)
beads_app.command(name="unschedule")(poller.unschedule)
