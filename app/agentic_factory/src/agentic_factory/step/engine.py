import asyncio
import json
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from agentic_factory.event import Event, EventKind, Observer
from agentic_factory.failure import BadOutput, TimedOut
from agentic_factory.settings.load import settings
from agentic_factory.step.catalog import client_for
from agentic_factory.step.client import Answer, Client
from agentic_factory.step.contract import Step, StepResult


async def run(step: Step, observer: Observer, client: Client | None = None) -> StepResult:
    """Run one llm step to its end: send it, show the answer to the observer,
    and either return the result or raise the `JobFailed` subclass that says
    why there is none."""
    client = client or client_for(step.provider)
    step = _prepare(step, client)
    started = monotonic()
    answer = await _complete(client, step)
    await _show(observer, EventKind.AI, answer)
    output = _parse_object(answer.text)  # after the ai event, so a bad answer is still logged
    await _show(observer, EventKind.FINISHED, answer)
    return StepResult(
        output=output,
        model=step.model,
        tokens=answer.tokens,
        duration_sec=monotonic() - started,
    )


def _prepare(step: Step, client: Client) -> Step:
    """The step as the client will get it: the client's model when none is named."""
    if not step.model:
        return step.model_copy(update={"model": client.default_model})
    return step


async def _complete(client: Client, step: Step) -> Answer:
    """The client's answer, or `TimedOut` past the step's own limit."""
    try:
        return await asyncio.wait_for(client.complete(step), timeout=step.timeout_sec)
    except TimeoutError:
        raise TimedOut(f"exceeded {step.timeout_sec}s") from None


async def _show(observer: Observer, kind: EventKind, answer: Answer) -> None:
    """The answer as one event: its text for AI, its usage only for FINISHED."""
    content = answer.text if kind == EventKind.AI else ""
    await observer.on_event(
        Event(kind=kind, at=datetime.now(tz=UTC), content=content, usage=answer.tokens)
    )


def _parse_object(text: str) -> dict[str, Any]:
    clip = settings.step.error_clip_chars
    try:
        output = json.loads(text)
    except json.JSONDecodeError as error:
        raise BadOutput(f"answer is not JSON ({error}): {text[:clip]}") from None
    if not isinstance(output, dict):
        raise BadOutput(f"answer is not a JSON object: {text[:clip]}")
    return output
