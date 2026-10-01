import asyncio
from pathlib import Path

from pydantic import BaseModel
from temporalio import activity
from temporalio.exceptions import ApplicationError

from distill import fetch
from distill.contract import DistillRequest, FetchedSource
from distill.sources import SourceError
from distill.verify import verify_research_dir


class FetchRequest(BaseModel):
    """Request plus where this run keeps its files."""

    request: DistillRequest
    work_dir: str


@activity.defn
async def fetch_source(request: FetchRequest) -> FetchedSource:
    """App fetch under the run work dir; only transient errors retry."""
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
    """App check over the entry folder: one problem per string."""
    return await asyncio.to_thread(verify_research_dir, Path(research_dir))
