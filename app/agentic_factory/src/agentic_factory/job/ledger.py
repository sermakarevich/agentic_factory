from agentic_factory.event import Event, EventKind
from agentic_factory.job.stats import JobStats
from agentic_factory.job.summary.block import find_summary_block


class Ledger:
    """What the engine keeps from the stream as it flows past: the counts,
    the coder's latest summary block and the `finished` event."""

    def __init__(self) -> None:
        self.stats = JobStats()
        self.summary_block = ""
        self.finished: Event | None = None

    def add(self, event: Event) -> None:
        self.stats.add(event)
        if event.kind == EventKind.FINISHED:
            self.finished = event
        elif event.kind == EventKind.AI and (block := find_summary_block(event.content)):
            self.summary_block = block
