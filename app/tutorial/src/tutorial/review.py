"""What follows a chapter's review: done, another rewrite, or failed for good."""

from enum import StrEnum

from tutorial.contract import Review


class Next(StrEnum):
    """The step after one review."""

    done = "done"
    rewrite = "rewrite"
    failed = "failed"


def after_review(review: Review, rewrites: int, review_rounds: int) -> Next:
    """Done when it passed; another rewrite while fewer than `review_rounds`
    were spent; failed once they all were."""
    if review.passed:
        return Next.done
    if rewrites < review_rounds:
        return Next.rewrite
    return Next.failed
