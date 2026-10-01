"""Every research prompt: one template per job, one function collecting the variables."""

import json
from pathlib import Path
from string import Template

from factory_settings import vault

from research.contract import Lens, SourceOutcome, Status, Subtopic
from research.run import Research
from research.settings.load import settings

FOLDER = Path(__file__).parent


def prompt(
    name: str, research: Research, subtopic: Subtopic | None = None, lens: Lens | None = None
) -> str:
    """The template `name` (a job: discover, assign, topic, digest, overview,
    agreements, disagreements, open_questions, lens, index) filled for this run."""
    return _rendered(FOLDER, name, values(research, subtopic, lens))


def values(
    research: Research, subtopic: Subtopic | None = None, lens: Lens | None = None
) -> dict[str, object]:
    """Every variable any template names. With a sub-topic the fresh sources
    and the resolution table are its own, else the whole run's."""
    request = research.request
    plan = research.plan
    per_source = settings.research
    fresh = research.fresh_of(subtopic) if subtopic else plan.fresh
    outcomes = research.outcomes_of(subtopic) if subtopic else research.sources
    return {
        "topics": ", ".join(request.topics),
        "topic_slugs": " ".join(request.topics),
        "focus": request.focus,
        "target": request.target,
        "topic": request.topic,
        "n_sources": request.n_sources,
        "lenses": ", ".join(request.lenses),
        "date_from": request.date_from,
        "kinds": ", ".join(request.kinds),
        "target_dir": research.target_dir,
        "research_dir": str(vault.research_dir()),
        "investment_dir": str(vault.investment_dir()),
        "research_topics_dir": str(vault.research_topics_dir()),
        "topic_page": str(research.topic_page),
        "candidates_min": request.n_sources * per_source.candidates_per_source_min,
        "candidates_max": request.n_sources * per_source.candidates_per_source_max,
        "abstract_chars": per_source.abstract_chars,
        "ranked": json.dumps(research.ranked_rows()),
        "shortlist_table": _shortlist_table(research),
        "source_table": _source_table(outcomes),
        "fresh": json.dumps([source.model_dump() for source in fresh]),
        "linked": json.dumps([source.model_dump() for source in plan.linked]),
        "source_count": research.source_count,
        "date_range": research.date_range,
        "nn": subtopic.nn if subtopic else "",
        "subtopic": subtopic.subtopic if subtopic else "",
        "title": subtopic.title if subtopic else "",
        "source_keys": " ".join(subtopic.sources) if subtopic else "",
        "linked_origins": " ".join(subtopic.linked) if subtopic else "",
        "lens": lens.lens if lens else "",
        "audience": lens.audience if lens else "",
    }


def _source_table(outcomes: list[SourceOutcome]) -> str:
    """One `| # | url | status | folder |` row per distilled source, the
    reason in the status cell where a source was skipped."""
    rows = [
        f"| {number} | {item.url} | {_status_cell(item)} | {item.path} |"
        for number, item in enumerate(outcomes, start=1)
    ]
    return "\n".join(["| # | url | status | folder |", *rows])


def _status_cell(outcome: SourceOutcome) -> str:
    """The status, with the reason when the source was skipped."""
    if outcome.reason:
        return f"{outcome.status.value}: {outcome.reason}"
    return outcome.status.value


def _shortlist_table(research: Research) -> str:
    """The ledger rows: every ranked candidate with its score, then the
    already-in-the-KB matches. The sub-topic column stays empty: the
    assignment lives in the plan, not the ranking."""
    rows = []
    for number, item in enumerate(research.candidates, start=1):
        if item.status == Status.in_kb or item.scores is None:
            rows.append(f"| {number} | {item.status.value} | {item.kind} |  | {item.title} |  |")
        else:
            rows.append(
                f"| {number} | {item.status.value} | {item.scores.kind} | "
                f"{item.scores.relevance:g} | {item.title} |  |"
            )
    return "\n".join(["| # | status | kind | score | source | sub-topic |", *rows])


def _rendered(folder: Path, name: str, values: dict[str, object]) -> str:
    """The template `name.md` in `folder` with `values` filled in."""
    text = (folder / f"{name}.md").read_text(encoding="utf-8")
    return Template(text).substitute(values)
