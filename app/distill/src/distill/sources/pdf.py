import html
import re
import shutil
import subprocess
import urllib.parse
from pathlib import Path

from distill.contract import SourceKind
from distill.settings.load import settings
from distill.sources.cli import run
from distill.sources.detect import ARXIV_ID_RE
from distill.sources.http import get
from distill.sources.source import Source, SourceError


def fetch(url: str, work_dir: Path) -> Source:
    """Download the PDF into `work_dir` and extract its text with pdftotext."""
    if shutil.which("pdftotext") is None:
        raise SourceError("pdf: `pdftotext` (poppler) is not installed")
    body, _ = get(_pdf_url(url))
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / "source.pdf"
    path.write_bytes(body)
    text = run(["pdftotext", "-layout", str(path), "-"], what="pdf text")
    title = _arxiv_title(url) or pdf_title(path, text)
    return Source(url=url, kind=SourceKind.pdf, title=title, text=text, tool="pdftotext")


def pdf_title(path: Path, text: str) -> str:
    """PDF metadata title when present, else the first non-empty text line."""
    if shutil.which("pdfinfo") is not None:
        try:
            info = subprocess.run(
                ["pdfinfo", str(path)],
                capture_output=True,
                text=True,
                timeout=settings.fetch.http_timeout_sec,
                check=False,
            ).stdout
        except subprocess.TimeoutExpired:
            info = ""
        for line in info.splitlines():
            if line.startswith("Title:") and line[6:].strip():
                return line[6:].strip()[: settings.fetch.title_chars]
    first = next((line.strip() for line in text.splitlines() if line.strip()), path.name)
    return first[: settings.fetch.title_chars]


def _pdf_url(url: str) -> str:
    """arXiv abs/html links point at the PDF; other URLs are used as given."""
    match = ARXIV_ID_RE.search(url)
    if match is not None:
        return f"https://arxiv.org/pdf/{match.group(1)}"
    return url


def _arxiv_title(url: str) -> str:
    """Title from the arXiv API for arXiv links; "" for other URLs or on failure."""
    match = ARXIV_ID_RE.search(url)
    if match is None:
        return ""
    query = urllib.parse.urlencode({"id_list": match.group(1)})
    try:
        body, _ = get(f"https://export.arxiv.org/api/query?{query}")
    except SourceError:
        return ""
    found = re.search(r"<entry>.*?<title>(.*?)</title>", body.decode("utf-8", "replace"), re.DOTALL)
    if found is None:
        return ""
    return " ".join(html.unescape(found.group(1)).split())[: settings.fetch.title_chars]
