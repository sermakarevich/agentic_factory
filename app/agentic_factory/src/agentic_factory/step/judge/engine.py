import asyncio
from datetime import UTC, datetime
from time import monotonic

from pydantic import TypeAdapter

from agentic_factory.callback import Callback
from agentic_factory.event import Event, EventKind
from agentic_factory.failure import TimedOut
from agentic_factory.step.judge.answer import Answer
from agentic_factory.step.judge.client import JudgeClient, JudgeReply
from agentic_factory.step.judge.contract import Judgment, JudgmentResult
from agentic_factory.step.judge.defaults import with_default_model

ANSWERS = TypeAdapter(dict[str, Answer])


async def run(judgment: Judgment, callback: Callback, client: JudgeClient) -> JudgmentResult:
    """Run one judge step to its end: send it, show the answers to the
    callback (as events; a step has no start and end of its own), and
    either return the result or raise the `JobFailed` subclass that says
    why there is none. The caller picks the client (`judge_for`)."""
    judgment = with_default_model(judgment, client)
    started = monotonic()
    reply = await _reply_within_timeout(client, judgment)
    await callback.on_event(_reply_as_event(EventKind.AI, reply))
    await callback.on_event(_reply_as_event(EventKind.FINISHED, reply))
    return JudgmentResult(
        answers=reply.answers,
        model=judgment.model,
        tokens=reply.tokens,
        cost_usd=reply.cost_usd,
        duration_sec=monotonic() - started,
    )


async def _reply_within_timeout(client: JudgeClient, judgment: Judgment) -> JudgeReply:
    """The judge's reply, or `TimedOut` past the judgment's own limit."""
    try:
        return await asyncio.wait_for(client.answer(judgment), timeout=judgment.timeout_sec)
    except TimeoutError:
        raise TimedOut(f"exceeded {judgment.timeout_sec}s") from None


def _reply_as_event(kind: EventKind, reply: JudgeReply) -> Event:
    """The reply as one event: the answers as JSON for AI, the bill only for FINISHED."""
    content = ANSWERS.dump_json(reply.answers).decode() if kind == EventKind.AI else ""
    return Event(
        kind=kind,
        at=datetime.now(tz=UTC),
        content=content,
        usage=reply.tokens,
        cost_usd=reply.cost_usd,
    )
