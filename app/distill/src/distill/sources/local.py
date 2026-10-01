import shutil
from pathlib import Path

from distill.contract import SourceKind
from distill.settings.load import settings
from distill.sources.cli import run
from distill.sources.detect import detect, local_path
from distill.sources.pdf import pdf_title
from distill.sources.source import Source, SourceError


def fetch(url: str, work_dir: Path) -> Source:
    """Read a local file off disk: PDFs through pdftotext, text as-is."""
    path = local_path(url)
    if path is None:
        raise SourceError(f"fetch {url}: not a local path")
    kind = detect(url)
    if not path.is_file():
        raise SourceError(f"fetch {url}: no such file")
    if path.stat().st_size > settings.fetch.max_bytes:
        raise SourceError(f"fetch {url}: file exceeds {settings.fetch.max_bytes} bytes")
    work_dir.mkdir(parents=True, exist_ok=True)
    staged = work_dir / f"source{path.suffix.lower()}"
    if path.resolve() != staged.resolve():
        staged.write_bytes(path.read_bytes())
    if kind is SourceKind.pdf:
        if shutil.which("pdftotext") is None:
            raise SourceError("pdf: `pdftotext` (poppler) is not installed")
        text = run(["pdftotext", "-layout", str(staged), "-"], what="pdf text")
        return Source(
            url=url, kind=kind, title=pdf_title(staged, text), text=text, tool="pdftotext"
        )
    text = staged.read_text(encoding="utf-8", errors="replace")
    if len(text.strip()) < settings.fetch.min_text_chars:
        raise SourceError(f"fetch {url}: file yielded only {len(text)} characters of text")
    first = next((line.strip() for line in text.splitlines() if line.strip()), path.name)
    return Source(
        url=url,
        kind=kind,
        title=first[: settings.fetch.title_chars],
        text=text,
        tool="local-file",
    )
