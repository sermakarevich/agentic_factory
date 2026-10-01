"""The explainer job: the entry in plain language."""

from pathlib import Path

from distill.contract import DistillRequest, EntryPlan, FetchedSource
from distill.prompts.template import rendered


def explainer_prompt(request: DistillRequest, fetched: FetchedSource, plan: EntryPlan) -> str:
    return rendered(Path(__file__).parent, "explainer", values(request, fetched, plan))


def values(request: DistillRequest, fetched: FetchedSource, plan: EntryPlan) -> dict[str, object]:
    """The template variables for the request, the fetched source, and the plan."""
    return {
        "title": fetched.title,
        "url": request.url,
        "work_dir": fetched.work_dir,
        "research_dir": plan.research_dir,
    }
