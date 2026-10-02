import json
from datetime import UTC, datetime
from pathlib import Path

from distill.chunking import Chunk, chunk_chars_in_bounds
from distill.chunking.repo import chunk_repo
from distill.chunking.text import chunk_text
from distill.contract import DistillRequest, FetchedChunk, FetchedSource, SourceKind
from distill.settings.load import settings
from distill.sources import Source, SourceError, fetch
from distill.topics import validate_topic

NO_CONTENT = (
    "source has no substantive content after README boilerplate "
    "(Sponsor, License, Star History, ...) was dropped: not worth an entry"
)


def fetch_source(request: DistillRequest, work_dir: Path) -> FetchedSource:
    """The source behind the request, fetched and chunked under `work_dir`."""
    topic = validate_topic(request.topic, Path(request.root)) if request.topic else ""
    base = _made_dir(work_dir)
    source = fetch(request.url.strip(), base)
    fetched_at = datetime.now(UTC).isoformat()
    source_md = _written_source(base, source, fetched_at, request.research_target, topic)
    chunks = _chunks_of(source, base, chunk_chars_in_bounds(request.chunk_chars))
    if not chunks:
        raise SourceError(f"fetch {request.url}: {NO_CONTENT}")
    return FetchedSource(
        work_dir=str(base),
        source_md=str(source_md),
        source_pdf=_existing(base / "source.pdf"),
        repo_dir=_existing(base / "repo"),
        title=source.title,
        kind=source.kind,
        fetched_at=fetched_at,
        chunks=_written_chunks(base, chunks),
    )


def work_dir_for(run_id: str) -> Path:
    """Where one run keeps its source.md, chunks/ and downloads."""
    return Path(settings.fetch.work_root).expanduser() / run_id


def _made_dir(work_dir: Path) -> Path:
    """The work dir, created, as an absolute path."""
    work = work_dir.expanduser()
    work.mkdir(parents=True, exist_ok=True)
    return work.resolve()


def _written_source(
    base: Path, source: Source, fetched_at: str, research_target: str, topic: str
) -> Path:
    """`source.md`: the provenance header the plan job reads, then the text."""
    lines = [
        f"# {source.title}",
        f"Source: {source.url}",
        f"Kind: {source.kind.value}",
        f"Fetched: {fetched_at}",
        f"Tool: {source.tool}",
    ]
    if research_target:
        lines.append(f"Research-Target: {research_target}")
    if topic:
        lines.append(f"Topic: {topic}")
    path = base / "source.md"
    path.write_text("\n".join(lines) + f"\n\n{source.text}\n", encoding="utf-8")
    return path


def _chunks_of(source: Source, base: Path, target: int) -> list[Chunk]:
    """A clone is cut per component, anything else by its headings."""
    if source.kind is SourceKind.repo and (base / "repo").is_dir():
        return chunk_repo(base / "repo", target)
    return chunk_text(source.text, target)


def _written_chunks(base: Path, chunks: list[Chunk]) -> list[FetchedChunk]:
    """One `chunks/<slug>.md` per chunk, and `chunks.json` listing them."""
    chunk_dir = base / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for chunk in chunks:
        path = chunk_dir / f"{chunk.slug}.md"
        path.write_text(f"# {chunk.title}\n\n{chunk.text}\n", encoding="utf-8")
        records.append(
            FetchedChunk(
                index=chunk.index,
                slug=chunk.slug,
                title=chunk.title,
                path=str(path),
                chars=len(chunk.text),
            )
        )
    listing = [record.model_dump() for record in records]
    (base / "chunks.json").write_text(json.dumps(listing, indent=2) + "\n", encoding="utf-8")
    return records


def _existing(path: Path) -> str:
    """The path as text when something is there, else empty."""
    return str(path) if path.exists() else ""
