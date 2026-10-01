"""The research activities: the run's folder made, the candidates file read.
Both fail at once on a bad input, no retry: another try meets the same input."""

from pathlib import Path

from research.contract import Discovered, ResearchRequest
from research.run import ensured_target_dir
from temporalio import activity
from temporalio.exceptions import ApplicationError

from distill.topics import validate_topic


@activity.defn
async def locate_target(request: ResearchRequest) -> str:
    """The topic checked as the child distill runs check it, then the run's
    folder made: its absolute path."""
    try:
        validate_topic(request.topic)
    except ValueError as error:
        raise ApplicationError(str(error), type="BadTopic", non_retryable=True) from error
    return str(ensured_target_dir(request))


@activity.defn
async def read_candidates(path: str) -> Discovered:
    """The candidates at `path`, validated as the discover job wrote them."""
    try:
        return Discovered.model_validate_json(Path(path).read_text())
    except (OSError, ValueError) as error:
        raise ApplicationError(
            f"candidates file {path} cannot be read: {error}",
            type="BadCandidates",
            non_retryable=True,
        ) from error
