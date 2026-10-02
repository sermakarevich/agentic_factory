"""The `af beads` typer group: every beads command registered on it, and every
other one forwarded to `bd`."""

import typer

from temporal_agentic_factory.cli.beads import database, forward, poller, submit, watcher

beads_app = typer.Typer(
    rich_markup_mode=None,  # help shows [table] names as typed, not as rich tags
    cls=forward.ForwardingGroup,
    no_args_is_help=True,
    help="Beads: submit beads to the database af owns, pull them as jobs."
    " Commands af does not define go to `bd`.",
)

beads_app.command(name="init")(database.init)
beads_app.command(name="add")(submit.add)
beads_app.command(name="set")(submit.set_job)
beads_app.command(name="retry")(submit.retry)
beads_app.command(name="list")(database.list_beads)
beads_app.command(name="show")(database.show)
beads_app.command(name="close")(database.close)
beads_app.command(name="ready")(poller.ready)
beads_app.command(name="poll")(poller.poll)
beads_app.command(name="start")(watcher.start)
beads_app.command(name="stop")(watcher.stop)
beads_app.command(name="restart")(watcher.restart)
beads_app.command(name="status")(watcher.status)
beads_app.command(
    name=forward.BD,
    cls=forward.VerbatimCommand,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)(forward.bd)
