"""A request names slugs for its folders, a question for its focus, and takes
its counts from settings unless told."""

import pytest
from pydantic import ValidationError

from research.contract import Discovered, PlannedSource, ResearchPlan, ResearchRequest, Status
from research.settings.load import settings


def _request(**overrides: object) -> ResearchRequest:
    values: dict[str, object] = {
        "topics": ["agents"],
        "focus": "What works for coding agents?",
        "target": "first-pass",
        "topic": "agents",
    }
    values.update(overrides)
    return ResearchRequest(**values)  # type: ignore[arg-type]


def test_counts_default_from_settings() -> None:
    request = _request()
    assert request.n_sources == settings.research.n_sources
    assert request.lenses == settings.research.lenses


def test_an_empty_topics_list_is_refused() -> None:
    with pytest.raises(ValidationError, match="topics"):
        _request(topics=[])


@pytest.mark.parametrize("topics", [["has/slash"], [""], ["."], [".."]])
def test_a_topic_slug_holds_no_path(topics: list[str]) -> None:
    with pytest.raises(ValidationError, match="topics"):
        _request(topics=topics)


@pytest.mark.parametrize("focus", ["", "   "])
def test_a_focus_is_a_question(focus: str) -> None:
    with pytest.raises(ValidationError, match="focus"):
        _request(focus=focus)


@pytest.mark.parametrize("target", ["", "has/slash", ".", ".."])
def test_a_target_is_one_folder(target: str) -> None:
    with pytest.raises(ValidationError, match="target"):
        _request(target=target)


@pytest.mark.parametrize("topic", ["Agents", "has space", "9lives", "has/slash", ""])
def test_a_topic_is_snake_case(topic: str) -> None:
    with pytest.raises(ValidationError, match="topic"):
        _request(topic=topic)


def test_a_good_request_keeps_what_it_was_given() -> None:
    request = _request(topics=["agents", "evals"], n_sources=4, lenses=["tech"])
    assert request.topics == ["agents", "evals"]
    assert request.n_sources == 4
    assert request.lenses == ["tech"]


def _source(key: str, origin: str = "") -> PlannedSource:
    return PlannedSource(
        key=key,
        url=f"https://example.com/{key}",
        title=key,
        kind="paper",
        subtopic="a",
        origin=origin,
    )


def test_a_plan_splits_its_sources_by_origin() -> None:
    plan = ResearchPlan(
        sources=[_source("src-01"), _source("kb-01", "research/Old"), _source("src-02")],
        subtopics=[],
        lenses=[],
    )

    assert [source.key for source in plan.fresh] == ["src-01", "src-02"]
    assert [source.key for source in plan.linked] == ["kb-01"]
    assert "fresh" not in ResearchPlan.model_json_schema()["properties"]


def test_a_discovered_file_reads_candidates_with_no_scores() -> None:
    text = (
        '{"candidates": [{"url": "u", "title": "t", "kind": "paper", "authors": "a", '
        '"date": "2026-01-01", "venue": "v", "abstract": "x", "status": "in_kb", '
        '"origin": "research/Old"}]}'
    )

    (candidate,) = Discovered.model_validate_json(text).candidates

    assert candidate.status == Status.in_kb and candidate.scores is None


def test_a_list_of_authors_is_joined_into_one_line() -> None:
    text = (
        '{"candidates": [{"url": "u", "title": "t", "kind": "paper", "authors": ["A", "B"], '
        '"date": "2026-01-01", "venue": "v", "abstract": "x", "status": "candidate"}]}'
    )

    (candidate,) = Discovered.model_validate_json(text).candidates

    assert candidate.authors == "A, B"
