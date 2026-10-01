"""The fetch of a distill source, as an activity: the app's fetch under the
run's work dir, run on a thread so the worker keeps polling while it
blocks on the network."""

import asyncio
from pathlib import Path

from pydantic import BaseModel
from temporalio import activity
from temporalio.exceptions import ApplicationError

from distill import fetch
from distill.contract import DistillRequest, FetchedSource
from distill.sources import SourceError


class FetchRequest(BaseModel):
    """What the fetch needs: the request, and where this run keeps its files."""

    request: DistillRequest
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
