"""The cli's handle on the configured beads database, with clean failures."""

from collections.abc import Iterator
from contextlib import contextmanager

from temporal_agentic_factory.cli.errors import fail
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.client import BeadsClient
from temporal_agentic_factory.watchers.beads.home import configured_home
from temporal_agentic_factory.watchers.beads.shell import BeadsError, run_bd


def configured() -> BeadsClient:
    """The client on `[beads].home`, initialised or not: `af beads init` makes it."""
    return BeadsClient(configured_home(), settings.beads.command_timeout_sec, run_bd)


def opened() -> BeadsClient:
    """The client on an initialised database; a clean exit, naming `af beads init`, if not."""
    client = configured()
    with beads_failures():
        client.require_initialised()
    return client


@contextmanager
def beads_failures() -> Iterator[None]:
    """A failed `bd` call as one stderr line and exit 1, no traceback."""
    try:
        yield
    except BeadsError as error:
        fail(str(error))
