from dataclasses import replace
from pathlib import Path

from distill.contract import SourceKind
from distill.sources import article, detect, local, pdf, repo, x, youtube
from distill.sources.source import Source, SourceError

__all__ = ["Source", "SourceError", "fetch"]


def fetch(url: str, work_dir: Path) -> Source:
    """Fetch one URL by its detected route; `work_dir` receives downloads."""
    if detect.local_path(url) is not None:
        return _sanitized(local.fetch(url, work_dir))
    routes = {
        SourceKind.youtube: youtube.fetch,
        SourceKind.x: x.fetch,
        SourceKind.pdf: pdf.fetch,
        SourceKind.repo: repo.fetch,
        SourceKind.article: article.fetch,
    }
    return _sanitized(routes[detect.detect(url)](url, work_dir))


def _sanitized(source: Source) -> Source:
    """Drop NUL bytes, which `pdftotext` interleaves and prompts refuse."""
    if "\x00" not in source.title and "\x00" not in source.text:
        return source
    return replace(
        source,
        title=source.title.replace("\x00", ""),
        text=source.text.replace("\x00", ""),
    )
