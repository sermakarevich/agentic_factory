from pathlib import Path

from distill.contract import SourceKind
from distill.settings.load import settings
from distill.sources.cli import run
from distill.sources.source import Source


def fetch(url: str, work_dir: Path) -> Source:
    """Tweet or thread as markdown through the `x` CLI (costs paid credits)."""
    text = run(["x", "tweet", url, "--thread", "--format", "md"], what="x thread", kind="x")
    first = next((line.strip("# ").strip() for line in text.splitlines() if line.strip()), url)
    return Source(
        url=url, kind=SourceKind.x, title=first[: settings.fetch.title_chars], text=text, tool="x"
    )
