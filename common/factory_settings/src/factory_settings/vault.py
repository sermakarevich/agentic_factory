"""The knowledge-base folders every prompt and the fetch step point at, as
absolute paths. Settings hold them with `~`; only this module expands it."""

from pathlib import Path

from factory_settings.shared import shared


def workdir() -> Path:
    """The knowledge-base repo: where every distill job runs."""
    return Path(shared.vault.workdir).expanduser()


def research_dir() -> Path:
    """Where an entry with no topic lands, as research/<PascalName>."""
    return Path(shared.vault.research).expanduser()


def investment_dir() -> Path:
    """Where a finance entry lands, as investment/<YYYY-MM-DD>-<PascalName>."""
    return Path(shared.vault.investment).expanduser()


def research_topics_dir() -> Path:
    """One folder per topic; a filed entry moves under its topic."""
    return Path(shared.vault.research_topics).expanduser()


def chosen_root(value: str) -> str:
    """A research_topics root chosen for one run, `~` expanded; refused unless absolute."""
    root = Path(value).expanduser()
    if not root.is_absolute():
        raise ValueError(f"root must be an absolute path, got {value!r}")
    return str(root)
