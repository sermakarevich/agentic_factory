"""The ranking: the questions the judge gets, the answers as scores, relevance
first with kind then authority on ties, the KB matches passed through."""

import pytest

from research.contract import Candidate, Scores, Status
from research.rank import judge_questions, ranked, scored


def _candidate(title: str, status: Status = Status.candidate) -> Candidate:
    return Candidate(
        url=f"https://example.com/{title}",
        title=title,
        kind="paper",
        authors="Ada",
        date="2026-01-01",
        venue="arXiv",
        abstract="Abstract.",
        status=status,
    )


def _answered(title: str, relevance: float, kind: str, authority: str) -> Candidate:
    scores = Scores(relevance=relevance, kind=kind, authority=authority)
    return _candidate(title).model_copy(update={"scores": scores})


def _statuses(items: list[Candidate]) -> dict[str, str]:
    return {item.title: item.status.value for item in items}


def test_the_questions_have_the_judge_shape_with_the_focus_filled() -> None:
    questions = judge_questions("agents for review")

    assert list(questions) == ["relevance", "kind", "authority"]
    assert questions["relevance"]["kind"] == "score" and len(questions["relevance"]["levels"]) == 4
    assert questions["kind"]["kind"] == "choice" and len(questions["kind"]["options"]) >= 2
    assert questions["authority"]["kind"] == "choice"
    assert "agents for review" in questions["relevance"]["question"]
    assert "{focus}" not in questions["relevance"]["question"]


def test_the_answers_become_scores() -> None:
    answers = {"relevance": 3.0, "kind": "survey", "authority": "unknown"}

    candidate = scored(_candidate("A"), answers)

    assert candidate.scores == Scores(relevance=1.0, kind="survey", authority="unknown")
    assert scored(_candidate("A"), {**answers, "relevance": 1.5}).scores.relevance == 0.5  # type: ignore[union-attr]


def test_the_best_score_comes_first_and_the_counts_split_the_rest() -> None:
    items = [
        _answered(title, relevance, "survey", "unknown")
        for title, relevance in [("a", 0.1), ("b", 0.9), ("c", 0.5), ("d", 0.7), ("e", 0.3)]
    ]

    result = ranked(items, n_sources=2, reserve_share=0.5)

    assert [item.title for item in result] == ["b", "d", "c", "e", "a"]
    assert _statuses(result) == {
        "b": "shortlist",
        "d": "shortlist",
        "c": "reserve",
        "e": "rejected",
        "a": "rejected",
    }


def test_kind_then_authority_break_ties() -> None:
    items = [
        _answered("opinion", 0.5, "opinion", "peer-reviewed"),
        _answered("blog", 0.5, "survey", "established-blog"),
        _answered("paper", 0.5, "survey", "peer-reviewed"),
    ]

    result = ranked(items, n_sources=3, reserve_share=0.0)

    assert [item.title for item in result] == ["paper", "blog", "opinion"]


def test_in_kb_matches_follow_unscored_and_fewer_than_n_all_shortlist() -> None:
    items = [_candidate("known", Status.in_kb), _answered("a", 0.5, "survey", "unknown")]

    result = ranked(items, n_sources=5, reserve_share=0.3)

    assert [item.title for item in result] == ["a", "known"]
    assert _statuses(result) == {"a": "shortlist", "known": "in_kb"}


def test_a_candidate_never_scored_is_refused() -> None:
    with pytest.raises(ValueError, match="never scored"):
        ranked([_candidate("A")], n_sources=1, reserve_share=0.0)
