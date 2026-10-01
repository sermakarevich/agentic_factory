"""After a review: done when it passed, rewrite while rounds are left, failed after."""

import pytest

from tutorial.contract import Review
from tutorial.review import Next, after_review

PASSED = Review(passed=True)
FAILED = Review(passed=False, problems=["the notebook does not run"])


@pytest.mark.parametrize("rewrites", [0, 1, 2])
def test_a_passed_review_is_done_whatever_the_round(rewrites: int) -> None:
    assert after_review(PASSED, rewrites, review_rounds=2) == Next.done


def test_a_failed_review_is_rewritten_while_rounds_are_left() -> None:
    assert after_review(FAILED, 0, review_rounds=2) == Next.rewrite
    assert after_review(FAILED, 1, review_rounds=2) == Next.rewrite


def test_a_failed_review_after_the_last_round_is_failed() -> None:
    assert after_review(FAILED, 2, review_rounds=2) == Next.failed


def test_no_rounds_means_one_review_only() -> None:
    assert after_review(FAILED, 0, review_rounds=0) == Next.failed
