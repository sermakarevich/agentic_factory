import json
import urllib.parse
from pathlib import Path

from distill.contract import SourceKind
from distill.sources.cli import run
from distill.sources.http import get
from distill.sources.source import Source, SourceError


def fetch(url: str, work_dir: Path) -> Source:
    """Transcript through the `yt` CLI; title through YouTube's oEmbed endpoint."""
    text = run(
        ["yt", "transcript", url, "--format", "txt"], what="youtube transcript", kind="youtube"
    )
    return Source(url=url, kind=SourceKind.youtube, title=_title(url), text=text, tool="yt")


def _title(url: str) -> str:
    """Video title from oEmbed; the URL itself when that lookup fails."""
    query = urllib.parse.urlencode({"url": url, "format": "json"})
    try:
        body, _ = get(f"https://www.youtube.com/oembed?{query}")
        return str(json.loads(body).get("title") or url)
    except (SourceError, ValueError):
        return url
