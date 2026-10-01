import re
from dataclasses import dataclass

from distill.settings.load import settings


@dataclass(frozen=True, slots=True)
class Chunk:
    """One contiguous piece of the source with a short human title."""

    index: int
    title: str
    text: str

    @property
    def slug(self) -> str:
        """Kebab-case file stem, e.g. `03-attention-mechanism`."""
        kebab = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")
        base = kebab[: settings.chunking.slug_chars].strip("-") or "part"
        return f"{self.index:02d}-{base}"


def chunk_chars_in_bounds(value: int) -> int:
    """The requested chunk size, raised or lowered to the bounds settings allow."""
    return max(settings.chunking.chars_min, min(settings.chunking.chars_max, value))
