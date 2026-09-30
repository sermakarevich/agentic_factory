"""The two summarise steps that are not jobs, as activities: the fetch of a
source and the check of a finished entry. Both are plain functions of the
`summarise` app, run on a thread so the worker keeps polling while they
block on the network or the disk."""

import asyncio
from pathlib import Path

from pydantic import BaseModel
from temporalio import activity
from temporalio.exceptions import ApplicationError

from summarise import fetch
from summarise.contract import FetchedSource, SummariseRequest
from summarise.sources import SourceError
from summarise.verify import verify_research_dir


class FetchRequest(BaseModel):
    """What the fetch needs: the request, and where this run keeps its files."""

    request: SummariseRequest
    work_dir: str


@activity.defn
async def fetch_source(request: FetchRequest) -> FetchedSource:
    """The app's fetch under the run's work dir. A source error keeps its
    message; only a transient one (network, a busy tool) is worth a retry.
    A bad topic is final: the request itself is wrong."""
    try:
        return await asyncio.to_thread(fetch.fetch_source, request.request, Path(request.work_dir))
    except SourceError as error:
        raise ApplicationError(
            str(error), type="SourceError", non_retryable=not error.transient
        ) from error
    except ValueError as error:
        raise ApplicationError(str(error), type="BadTopic", non_retryable=True) from error


@activity.defn
async def verify_entry(research_dir: str) -> list[str]:
    """The app's check over the entry folder: one problem per string, none
    when the entry passes."""
    return await asyncio.to_thread(verify_research_dir, Path(research_dir))
