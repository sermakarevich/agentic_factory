import sys
from typing import TextIO

from agentic_factory.event import Event
from agentic_factory.job.callback import JobCallback, JobEnd


class JsonLinesCallback(JobCallback):
    """One JSON object per line, for a program to read: every event, then the
    end of the run. Written to `out` as is, with no timestamp in front of it,
    so the lines stay parseable; the human log goes to stderr, this to stdout."""

    def __init__(self, out: TextIO = sys.stdout) -> None:
        self.out = out

    async def on_event(self, event: Event) -> None:
        self._write(event.model_dump_json(exclude={"raw"}))

    async def on_end(self, end: JobEnd) -> None:
        self._write(end.model_dump_json(exclude={"result"}))

    def _write(self, line: str) -> None:
        self.out.write(line + "\n")
        self.out.flush()
