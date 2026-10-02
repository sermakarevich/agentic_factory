"""Every template renders from one run's state with no placeholder left."""

from pathlib import Path

import pytest

from research.contract import (
    Candidate,
    Lens,
    PlannedSource,
    ResearchPlan,
    ResearchRequest,
    Scores,
    SourceOutcome,
    SourceStatus,
    Status,
    Subtopic,
)
from research.prompts.prompt import FOLDER, prompt
from research.run import Research

SUBTOPIC = Subtopic(
    nn="01", subtopic="agents", title="Agents", sources=["src-01"], linked=["research/Old"]
)
LENS = Lens(lens="tech", audience="engineers")
RESEARCH = Research(
    request=ResearchRequest(
        topics=["agents", "evals"],
        focus="What works for coding agents?",
        target="first-pass",
        topic="agents",
    ),
    target_dir="/kb/research_topics/agents/research/first-pass",
    candidates=[
        Candidate(
            url="https://example.com/a",
            title="Alpha",
            kind="paper",
            authors="Ada",
            date="2026-01-01",
            venue="arXiv",
            abstract="About Alpha.",
            status=Status.shortlist,
            scores=Scores(relevance=0.9, kind="survey", authority="unknown"),
        )
    ],
    plan=ResearchPlan(
        sources=[
            PlannedSource(
                key="src-01",
                url="https://example.com/a",
                title="Alpha",
                kind="paper",
                subtopic="agents",
            ),
            PlannedSource(
                key="kb-01",
                url="https://example.com/old",
                title="Old",
                kind="article",
                subtopic="evals",
                origin="research/Old",
            ),
        ],
        subtopics=[SUBTOPIC],
        lenses=[LENS],
    ),
    sources=[
        SourceOutcome(
            key="src-01",
            url="https://example.com/a",
            title="Alpha",
            status=SourceStatus.succeeded,
            path="/kb/research_topics/agents/Alpha",
        )
    ],
)
NAMES = sorted(path.stem for path in FOLDER.glob("*.md"))


def test_every_job_has_a_template() -> None:
    assert NAMES == [
        "agreements",
        "assign",
        "digest",
        "disagreements",
        "discover",
        "index",
        "lens",
        "open_questions",
        "overview",
        "topic",
    ]


@pytest.mark.parametrize("name", NAMES)
def test_a_template_renders_with_no_placeholder_left(name: str) -> None:
    text = prompt(name, RESEARCH, subtopic=SUBTOPIC, lens=LENS)

    assert "$" not in text


def test_the_topic_prompt_carries_its_sources_and_the_resolution_table() -> None:
    text = prompt("topic", RESEARCH, subtopic=SUBTOPIC)

    assert "src-01" in text and "research/Old" in text
    assert "| 1 | https://example.com/a | succeeded | /kb/research_topics/agents/Alpha |" in text


def test_the_assign_prompt_carries_the_ranked_rows() -> None:
    text = prompt("assign", RESEARCH)

    assert '"shortlist": [{"url": "https://example.com/a"' in text
    assert "agents, evals" in text


def test_the_index_prompt_carries_the_ledger_and_the_topic_page() -> None:
    text = prompt("index", RESEARCH)

    assert "| 1 | shortlist | survey | 0.9 | Alpha |  |" in text
    assert "kb-01" in text and "agents/agents.md" in text


def test_the_prompts_point_at_the_root_the_run_chose(tmp_path: Path) -> None:
    request = RESEARCH.request.model_copy(update={"root": str(tmp_path)})
    research = RESEARCH.model_copy(update={"request": request})

    discover = prompt("discover", research)
    agreements = prompt("agreements", research)

    assert f"`{tmp_path}/*/research/*/index.md`" in discover
    assert f"`{tmp_path}/agents/<Name>/summary.md`" in agreements
    assert f"{tmp_path}/agents/agents.md" in prompt("index", research)
