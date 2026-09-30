from datetime import UTC, datetime

from agentic_factory.event import Event, EventKind
from agentic_factory.job.ledger import Ledger
from agentic_factory.tokens import Tokens

NOW = datetime(2026, 9, 30, tzinfo=UTC)


def test_totals_are_summed_over_turns_until_finished_brings_the_coders_own() -> None:
    ledger = Ledger()
    ledger.add(Event(kind=EventKind.AI, at=NOW, usage=Tokens(input=10, output=1), cost_usd=0.1))
    ledger.add(Event(kind=EventKind.TOOL, at=NOW))
    ledger.add(Event(kind=EventKind.AI, at=NOW, usage=Tokens(input=20, output=2), cost_usd=0.2))
    assert ledger.tokens == Tokens(input=30, output=3) and ledger.cost_usd == 0.30000000000000004
    assert ledger.stats.turns == 2 and ledger.finished is None
    ledger.add(
        Event(kind=EventKind.FINISHED, at=NOW, usage=Tokens(input=31, output=3), cost_usd=0.5)
    )
    assert ledger.tokens == Tokens(input=31, output=3) and ledger.cost_usd == 0.5
    assert ledger.finished is not None


def test_a_finished_without_usage_keeps_the_sum() -> None:
    ledger = Ledger()
    ledger.add(Event(kind=EventKind.AI, at=NOW, usage=Tokens(input=10)))
    ledger.add(Event(kind=EventKind.FINISHED, at=NOW))
    assert ledger.tokens == Tokens(input=10)
