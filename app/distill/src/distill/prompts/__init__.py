from pathlib import Path
from string import Template

from factory_settings import vault
from pydantic import BaseModel

from distill.contract import DistillRequest, EntryPlan, FetchedChunk, FetchedSource
from distill.settings.load import settings

FOLDER = Path(__file__).parent


class Entry(BaseModel):
    request: DistillRequest
    fetched: FetchedSource
    plan: EntryPlan
    run_date: str


def plan_prompt(request: DistillRequest, fetched: FetchedSource, run_date: str) -> str:
    """Plan where the entry lives and state it."""
    text = _rendered(FOLDER, "plan", _values(request, fetched, run_date))
    if fetched.kind == "repo":
        text += _rendered(FOLDER, "plan_repo_track", {})
    return text


def page_prompt(name: str, entry: Entry) -> str:
    """One reader page: digest, summary, explainer, questions, critical_thinking, file."""
    return _rendered(
        FOLDER,
        _template(name, entry.fetched.kind),
        _values(entry.request, entry.fetched, entry.run_date, entry.plan),
    )


def wiki_prompt(entry: Entry, chunk: FetchedChunk) -> str:
    """One wiki page for one chunk."""
    return _rendered(
        FOLDER,
        _template("wiki", entry.fetched.kind),
        _values(
            entry.request,
            entry.fetched,
            entry.run_date,
            entry.plan,
            chunk_title=chunk.title,
            chunk_index=chunk.index,
            chunk_count=len(entry.fetched.chunks),
            chunk_path=chunk.path,
            chunk_slug=chunk.slug,
        ),
    )


def index_prompt(entry: Entry, problems: list[str]) -> str:
    """Folder index, plus minimal fixes when the verifier named problems."""
    values = _values(entry.request, entry.fetched, entry.run_date, entry.plan)
    text = _rendered(FOLDER, "index", values)
    if problems:
        values["problems"] = _listed(problems)
        text += _rendered(FOLDER, "index_feedback", values)
    return text


def _values(
    request: DistillRequest,
    fetched: FetchedSource,
    run_date: str,
    plan: EntryPlan | None = None,
    **extra: object,
) -> dict[str, object]:
    """Every variable any template can name."""
    values: dict[str, object] = {
        "title": fetched.title,
        "url": request.url,
        "kind": fetched.kind,
        "type": fetched.type,
        "work_dir": fetched.work_dir,
        "source_md": fetched.source_md,
        "research_dir": plan.research_dir if plan else "",
        "slug": plan.slug if plan else "",
        "run_date": run_date,
        "topic": request.topic,
        "research_target": request.research_target,
        "research": str(vault.research_dir()),
        "investment": str(vault.investment_dir()),
        "topic_dir": str(vault.research_topics_dir() / request.topic),
        "target_dir": request.target_dir,
        "pdf_mb": f"{settings.entry.pdf_copy_max_bytes / 1_000_000:g}",
        "min_bytes": settings.verify.min_bytes,
        "closing": _closing(fetched.kind),
        "problems": "",
    }
    values["folder_section"] = _folder_section(request, values)
    values.update(extra)
    return values


def _template(name: str, kind: str) -> str:
    """Repo variant when the kind is repo and that file exists."""
    if kind == "repo" and (FOLDER / f"{name}_repo.md").exists():
        return f"{name}_repo"
    return name


def _closing(kind: str) -> str:
    """Digest closing heading: the system for a clone, the argument otherwise."""
    if kind == "repo":
        return "The system in five moves"
    return "The argument in five moves"


def _folder_section(request: DistillRequest, values: dict[str, object]) -> str:
    """Fixed folder when the request names one, derived routing otherwise."""
    if request.target_dir:
        return _rendered(FOLDER, "plan_folder_fixed", values)
    return _rendered(FOLDER, "plan_folder_derived", values)


def _rendered(folder: Path, name: str, values: dict[str, object]) -> str:
    """The template `name.md` in `folder` with `values` filled in."""
    text = (folder / f"{name}.md").read_text(encoding="utf-8")
    return Template(text).substitute(values)


def _listed(problems: list[str]) -> str:
    """Verifier problems as dash-led lines."""
    return "\n".join(f"- {problem}" for problem in problems)
