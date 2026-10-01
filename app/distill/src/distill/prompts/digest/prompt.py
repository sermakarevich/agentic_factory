"""The digest job: every wiki page's one-sentence line and key points, verbatim."""

from pathlib import Path

from distill.contract import DistillRequest, EntryPlan, FetchedSource
from distill.prompts.template import rendered

CLOSING = {"repo": "The system in five moves", "text": "The argument in five moves"}


def digest_prompt(request: DistillRequest, fetched: FetchedSource, plan: EntryPlan) -> str:
    """The prompt; a clone's closing section traces the system, a text's the argument."""
    return rendered(
        Path(__file__).parent,
        "digest",
        {
            "title": fetched.title,
            "url": request.url,
            "work_dir": fetched.work_dir,
            "research_dir": plan.research_dir,
            "closing": closing_for(fetched.kind),
        },
    )


def closing_for(kind: str) -> str:
    """The closing heading for a repo clone or for any other source."""
    if kind == "repo":
        return CLOSING["repo"]
    return CLOSING["text"]
