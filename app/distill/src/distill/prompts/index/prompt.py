"""The index job: the entry's front page, and the fixes the verifier asks for."""

from pathlib import Path

from distill.contract import DistillRequest, EntryPlan, FetchedSource
from distill.prompts.template import rendered
from distill.settings.load import settings


def index_prompt(
    request: DistillRequest, fetched: FetchedSource, plan: EntryPlan, problems: list[str]
) -> str:
    """The prompt; with verifier problems from a failed check it also asks
    for the minimal fixes to the files they name."""
    text = rendered(Path(__file__).parent, "index", values(request, fetched, plan))
    if problems:
        text += rendered(Path(__file__).parent, "feedback", feedback_values(problems))
    return text


def values(request: DistillRequest, fetched: FetchedSource, plan: EntryPlan) -> dict[str, object]:
    """The template variables for the request, the fetched source, and the plan."""
    return {
        "title": fetched.title,
        "url": request.url,
        "work_dir": fetched.work_dir,
        "research_dir": plan.research_dir,
    }


def feedback_values(problems: list[str]) -> dict[str, object]:
    """The verifier's problems as one list, with the minimum size a file must pass."""
    return {"problems": listed(problems), "min_bytes": settings.verify.min_bytes}


def listed(problems: list[str]) -> str:
    """The verifier problems as dash-led lines."""
    return "\n".join(f"- {problem}" for problem in problems)
