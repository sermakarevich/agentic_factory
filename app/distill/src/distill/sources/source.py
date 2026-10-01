from dataclasses import dataclass

from distill.contract import SourceKind


class SourceError(Exception):
    """The source behind a URL could not be fetched or read."""

    def __init__(self, message: str, *, transient: bool = False) -> None:
        """Remember the message and whether retrying could help."""
        super().__init__(message)
        self.transient = transient


@dataclass(frozen=True, slots=True)
class Source:
    """Fetched source: its kind, a title hint and the full text as markdown."""

    url: str
    kind: SourceKind
    title: str
    text: str
    tool: str
