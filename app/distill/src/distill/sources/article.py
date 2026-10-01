import re
from pathlib import Path

from distill.contract import SourceKind
from distill.settings.load import settings
from distill.sources.detect import repo_root
from distill.sources.github import fetch as fetch_github
from distill.sources.html import MarkdownExtractor
from distill.sources.http import get
from distill.sources.source import Source, SourceError


def fetch(url: str, work_dir: Path) -> Source:
    """Web page stripped to text; PDFs served without .pdf go to pdftotext."""
    body, content_type = get(url)
    if "application/pdf" in content_type.lower() or body[:5] == b"%PDF-":
        raise SourceError(
            f"fetch {url}: served a PDF without a .pdf path; pass the PDF link directly"
        )
    repo = repo_root(url)
    if repo is not None:
        return fetch_github(url, repo[0], repo[1], body)
    parser = MarkdownExtractor()
    parser.feed(body.decode("utf-8", errors="replace"))
    text = parser.text()
    if len(text) < settings.fetch.min_text_chars:
        raise SourceError(f"fetch {url}: page yielded only {len(text)} characters of text")
    title = re.sub(r"\s+", " ", parser.title).strip() or url
    return Source(
        url=url,
        kind=SourceKind.article,
        title=title[: settings.fetch.title_chars],
        text=text,
        tool="urllib",
    )
