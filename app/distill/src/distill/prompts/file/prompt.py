"""The file job: move the finished entry under its topic and list it there."""

from pathlib import Path

from distill import vault
from distill.contract import DistillRequest, EntryPlan, FetchedSource
from distill.prompts.template import rendered


def file_prompt(request: DistillRequest, fetched: FetchedSource, plan: EntryPlan) -> str:
    """The prompt; the topic was validated before the run, so the job never asks."""
    return rendered(Path(__file__).parent, "file", values(request, fetched, plan))


def values(request: DistillRequest, fetched: FetchedSource, plan: EntryPlan) -> dict[str, object]:
    """The template variables with the topic folder the entry moves into."""
    return {
        "title": fetched.title,
        "url": request.url,
        "topic": request.topic,
        "research_dir": plan.research_dir,
        "work_dir": fetched.work_dir,
        "topic_dir": str(vault.research_topics_dir() / request.topic),
    }
