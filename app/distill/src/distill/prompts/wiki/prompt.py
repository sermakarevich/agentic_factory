"""The wiki jobs: one page per chunk, written in parallel."""

from pathlib import Path

from distill.contract import DistillRequest, EntryPlan, FetchedChunk, FetchedSource
from distill.prompts.template import rendered


def wiki_prompt(
    request: DistillRequest, fetched: FetchedSource, plan: EntryPlan, chunk: FetchedChunk
) -> str:
    """The prompt for one chunk's page: the component variant for a clone,
    the text variant for everything else."""
    folder = Path(__file__).parent
    return rendered(folder, template_for(fetched.kind), values(request, fetched, plan, chunk))


def template_for(kind: str) -> str:
    """The template variant for a repo clone or for any other source."""
    if kind == "repo":
        return "repo"
    return "text"


def values(
    request: DistillRequest, fetched: FetchedSource, plan: EntryPlan, chunk: FetchedChunk
) -> dict[str, object]:
    """The template variables for one chunk's page."""
    return {
        "chunk_title": chunk.title,
        "chunk_index": chunk.index,
        "chunk_count": len(fetched.chunks),
        "title": fetched.title,
        "url": request.url,
        "work_dir": fetched.work_dir,
        "chunk_path": chunk.path,
        "research_dir": plan.research_dir,
        "chunk_slug": chunk.slug,
    }
