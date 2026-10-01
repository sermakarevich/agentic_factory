"""The check of a finished entry, as an activity: the app's verifier over
the entry folder, run on a thread so the worker keeps polling while it
reads the disk."""

import asyncio
from pathlib import Path

from temporalio import activity

from distill.verify import verify_research_dir


@activity.defn
async def verify_entry(research_dir: str) -> list[str]:
    """The app's check over the entry folder: one problem per string, none
    when the entry passes."""
    return await asyncio.to_thread(verify_research_dir, Path(research_dir))
