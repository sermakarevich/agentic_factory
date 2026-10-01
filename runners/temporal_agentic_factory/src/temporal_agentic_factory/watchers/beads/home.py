"""Where the beads database af owns lives: `[beads].home`, `~` expanded."""

from pathlib import Path

from temporal_agentic_factory.settings.load import settings


def configured_home() -> Path:
    """The configured database home as an absolute path."""
    return Path(settings.beads.home).expanduser()
