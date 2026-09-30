from agentic_factory.event import Event, EventKind
from agentic_factory.job.stats import JobStats
from agentic_factory.job.summary.block import find_summary_block
from agentic_factory.tokens import Tokens


class Ledger:
    """What the engine keeps from the stream as it flows past: the counts,
    the tokens and cost so far, the coder's latest summary block and the
    `finished` event. The totals are summed over the turns until `finished`
    brings the coder's own, so a run that fails midway still has them."""

    def __init__(self) -> None:
        self.stats = JobStats()
        self.tokens = Tokens()
        self.cost_usd = 0.0
        self.summary_block = ""
        self.finished: Event | None = None

    @property
    def usage_known(self) -> bool:
        """True once `finished` brought the coder's own totals. Without them
        the tokens are the sum of the turns that carried usage, or zero."""
        return self.finished is not None and self.finished.usage is not None

    def add(self, event: Event) -> None:
        self.stats.add(event)
        match event.kind:
            case EventKind.FINISHED:
                self.finished = event
                self._take_totals(event)
            case EventKind.AI:
                self._add_turn(event)

    def _add_turn(self, event: Event) -> None:
        self.tokens = self.tokens + (event.usage or Tokens())
        self.cost_usd += event.cost_usd
        if block := find_summary_block(event.content):
            self.summary_block = block

    def _take_totals(self, finished: Event) -> None:
        """The coder's totals replace the sum: they are what it billed."""
        if finished.usage is not None:
            self.tokens = finished.usage
            self.cost_usd = finished.cost_usd
