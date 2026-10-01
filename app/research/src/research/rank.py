"""The ranking: the judge step's three questions, their answers turned into
scores, and the order of the scored candidates into shortlist, reserve, rejected."""

from copy import deepcopy
from math import ceil
from typing import Any

from research.contract import Candidate, Scores, Status

QUESTIONS: dict[str, dict[str, Any]] = {
    "relevance": {
        "kind": "score",
        "question": "How directly does this source answer the research focus: {focus}?",
        "levels": ["irrelevant", "tangential", "relevant", "central"],
    },
    "kind": {
        "kind": "choice",
        "question": "What kind of source is this?",
        "options": dict.fromkeys(
            ["primary-research", "survey", "tutorial", "opinion", "announcement"]
        ),
    },
    "authority": {
        "kind": "choice",
        "question": "How authoritative is the origin?",
        "options": dict.fromkeys(
            ["peer-reviewed", "recognised-lab-or-author", "established-blog", "unknown"]
        ),
    },
}

KIND_ORDER = ["primary-research", "survey", "tutorial", "announcement", "opinion"]
AUTHORITY_ORDER = ["peer-reviewed", "recognised-lab-or-author", "established-blog", "unknown"]


def judge_questions(focus: str) -> dict[str, dict[str, Any]]:
    """The three questions with the run's focus in the relevance one."""
    questions = deepcopy(QUESTIONS)
    relevance = questions["relevance"]
    relevance["question"] = relevance["question"].format(focus=focus)
    return questions


def scored(candidate: Candidate, answers: dict[str, float | str]) -> Candidate:
    """The candidate with its answers as scores: the relevance level index
    as 0-1, the kind and authority labels as picked."""
    top_level = len(QUESTIONS["relevance"]["levels"]) - 1
    scores = Scores(
        relevance=float(answers["relevance"]) / top_level,
        kind=str(answers["kind"]),
        authority=str(answers["authority"]),
    )
    return candidate.model_copy(update={"scores": scores})


def ranked(candidates: list[Candidate], n_sources: int, reserve_share: float) -> list[Candidate]:
    """The scored candidates by relevance desc, kind then authority on ties:
    the top n_sources shortlist, the next share reserve, the rest rejected;
    the in-KB matches follow, never scored."""
    known = [item for item in candidates if item.status == Status.in_kb]
    unscored = [item for item in candidates if item.status != Status.in_kb]
    ordered = sorted(unscored, key=order_key)
    shortlist_count = min(n_sources, len(ordered))
    reserve_count = min(ceil(n_sources * reserve_share), len(ordered) - shortlist_count)
    statuses = (
        [Status.shortlist] * shortlist_count
        + [Status.reserve] * reserve_count
        + [Status.rejected] * (len(ordered) - shortlist_count - reserve_count)
    )
    return [
        item.model_copy(update={"status": status})
        for item, status in zip(ordered, statuses, strict=True)
    ] + known


def order_key(candidate: Candidate) -> tuple[float, int, int]:
    """Relevance desc, then kind order, then authority order."""
    scores = candidate.scores
    if scores is None:
        raise ValueError(f"{candidate.url} was never scored")
    return (
        -scores.relevance,
        _position(KIND_ORDER, scores.kind),
        _position(AUTHORITY_ORDER, scores.authority),
    )


def _position(order: list[str], label: str) -> int:
    """Where the label sits in the order; unknown labels go last."""
    return order.index(label) if label in order else len(order)
