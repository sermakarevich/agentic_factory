import asyncio
import json
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from agentic_factory.callback import Callback
from agentic_factory.event import Event, EventKind
from agentic_factory.failure import BadOutput, TimedOut
from agentic_factory.settings.load import settings
from agentic_factory.step.contract import Step, StepResult
from agentic_factory.step.defaults import with_default_model
from agentic_factory.step.providers.client import Answer, Client


async def run(step: Step, callback: Callback, client: Client) -> StepResult:
    """Run one llm step to its end: send it, show the answer to the callback
    (as events; a step has no start and end of its own), and either return
    the result or raise the `JobFailed` subclass that says why there is none.
    The caller picks the client (`client_for`)."""
    step = with_default_model(step, client)
    started = monotonic()
    answer = await _answer_within_timeout(client, step)
    await callback.on_event(_answer_as_event(EventKind.AI, answer))
    output = _parse_object(answer.text)  # after the ai event, so a bad answer is still logged
    await callback.on_event(_answer_as_event(EventKind.FINISHED, answer))
    return StepResult(
        output=output,
        model=step.model,
        tokens=answer.tokens,
        duration_sec=monotonic() - started,
    )


async def _answer_within_timeout(client: Client, step: Step) -> Answer:
    """The client's answer, or `TimedOut` past the step's own limit."""
    try:
        return await asyncio.wait_for(client.complete(step), timeout=step.timeout_sec)
    except TimeoutError:
        raise TimedOut(f"exceeded {step.timeout_sec}s") from None


def _answer_as_event(kind: EventKind, answer: Answer) -> Event:
    """The answer as one event: its text for AI, its usage only for FINISHED."""
    content = answer.text if kind == EventKind.AI else ""
    return Event(kind=kind, at=datetime.now(tz=UTC), content=content, usage=answer.tokens)


def _parse_object(text: str) -> dict[str, Any]:
    clip = settings.step.error_clip_chars
    try:
        output = json.loads(text)
    except json.JSONDecodeError as error:
        raise BadOutput(f"answer is not JSON ({error}): {text[:clip]}") from None
    if not isinstance(output, dict):
        raise BadOutput(f"answer is not a JSON object: {text[:clip]}")
    return output
