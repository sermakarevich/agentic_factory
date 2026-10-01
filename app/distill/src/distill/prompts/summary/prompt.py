"""The summary job: the technical analysis of a clone, or the paper-style
summary of a text."""

from pathlib import Path

from distill.contract import DistillRequest, EntryPlan, FetchedSource
from distill.prompts.template import rendered


def summary_prompt(
    request: DistillRequest, fetched: FetchedSource, plan: EntryPlan, run_date: str
) -> str:
    """The prompt, with the run date as YYYY-MM-DD for the analysis's metadata line."""
    folder = Path(__file__).parent
    if fetched.kind == "repo":
        return rendered(folder, "technical_analysis", repo_values(request, fetched, plan, run_date))
    return rendered(folder, "text", text_values(request, fetched, plan))


def repo_values(
    request: DistillRequest, fetched: FetchedSource, plan: EntryPlan, run_date: str
) -> dict[str, object]:
    """The template variables for a clone's technical analysis."""
    return {
        "title": fetched.title,
        "url": request.url,
        "work_dir": fetched.work_dir,
        "research_dir": plan.research_dir,
        "run_date": run_date,
    }


def text_values(
    request: DistillRequest, fetched: FetchedSource, plan: EntryPlan
) -> dict[str, object]:
    """The template variables for a text source's summary."""
    return {
        "title": fetched.title,
        "url": request.url,
        "type": fetched.type,
        "work_dir": fetched.work_dir,
        "research_dir": plan.research_dir,
    }
