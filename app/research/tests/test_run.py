"""One run's state: the folder it lands in, the counts and ranges the prompts
carry, and the sub-topic slices."""

from pathlib import Path
from typing import Any

from research.contract import (
    Candidate,
    Lens,
    PlannedSource,
    ResearchPlan,
    ResearchRequest,
    SourceOutcome,
    SourceStatus,
    Status,
    Subtopic,
)
from research.run import Research, ensured_target_dir, target_dir

REQUEST = ResearchRequest(
    topics=["agents"], focus="What works?", target="first-pass", topic="agents"
)
SUBTOPIC = Subtopic(nn="01", subtopic="agents", title="Agents", sources=["src-01"], linked=[])


def _candidate(title: str, date: str, status: Status) -> Candidate:
    return Candidate(
        url=f"https://example.com/{title}",
        title=title,
        kind="paper",
        authors="Ada",
        date=date,
        venue="arXiv",
        abstract="Abstract.",
        status=status,
    )


def _source(key: str, origin: str = "") -> PlannedSource:
    return PlannedSource(
        key=key,
        url=f"https://example.com/{key}",
        title=key,
        kind="paper",
        subtopic="agents",
        origin=origin,
    )


def _outcome(key: str, status: SourceStatus) -> SourceOutcome:
    return SourceOutcome(key=key, url=f"https://example.com/{key}", title=key, status=status)


def _research(**fields: Any) -> Research:
    return Research(request=REQUEST, target_dir="/kb/t", **fields)


def test_the_run_lands_under_its_topic_in_the_root_asked_for(tmp_path: Path) -> None:
    request = REQUEST.model_copy(update={"root": str(tmp_path)})
    expected = tmp_path / "agents" / "research" / "first-pass"

    assert target_dir(request) == expected
    assert ensured_target_dir(request) == expected and expected.is_dir()
    research = Research(request=request, target_dir=str(expected))
    assert research.topic_page == tmp_path / "agents" / "agents.md"


def test_the_source_count_is_the_filed_and_the_linked() -> None:
    plan = ResearchPlan(
        sources=[_source("src-01"), _source("src-02"), _source("kb-01", "research/Old")],
        subtopics=[],
        lenses=[],
    )
    sources = [_outcome("src-01", SourceStatus.succeeded), _outcome("src-02", SourceStatus.skipped)]

    assert _research(plan=plan, sources=sources).source_count == 2


def test_the_date_range_runs_from_the_first_to_the_last_month() -> None:
    dated = [
        _candidate("a", "2026-03-02", Status.shortlist),
        _candidate("b", "2025-06-01", Status.in_kb),
        _candidate("c", "", Status.rejected),
    ]

    assert _research(candidates=dated).date_range == "2025-06 to 2026-03"
    assert _research(candidates=dated[:1]).date_range == "2026-03"
    assert _research().date_range == "undated"


def test_the_assign_job_reads_only_shortlist_and_reserve_rows() -> None:
    candidates = [
        _candidate("a", "", Status.shortlist),
        _candidate("b", "", Status.reserve),
        _candidate("c", "", Status.rejected),
        _candidate("d", "", Status.in_kb),
    ]

    rows = _research(candidates=candidates).ranked_rows()

    assert {name: [row["title"] for row in found] for name, found in rows.items()} == {
        "shortlist": ["a"],
        "reserve": ["b"],
    }


def test_a_subtopic_takes_its_own_fresh_sources_and_outcomes() -> None:
    plan = ResearchPlan(
        sources=[_source("src-01"), _source("src-02")],
        subtopics=[SUBTOPIC],
        lenses=[Lens(lens="tech", audience="engineers")],
    )
    sources = [_outcome("src-01", SourceStatus.succeeded), _outcome("src-02", SourceStatus.skipped)]
    research = _research(plan=plan, sources=sources)

    assert [source.key for source in research.fresh_of(SUBTOPIC)] == ["src-01"]
    assert [item.key for item in research.outcomes_of(SUBTOPIC)] == ["src-01"]
    assert [item.title for item in research.to_judge()] == []


def test_the_result_names_where_the_run_landed_and_what_it_made() -> None:
    research = _research(candidates=[_candidate("a", "2026-01-01", Status.shortlist)])

    result = research.researched("/kb/t/index.md")

    assert (result.target_dir, result.index_path) == ("/kb/t", "/kb/t/index.md")
    assert [item.title for item in result.candidates] == ["a"]
