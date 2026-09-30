import asyncio
import json
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from agent_factory.event import Event, EventKind, Observer
from agent_factory.failure import BadOutput, TimedOut
from agent_factory.settings.load import settings
from agent_factory.step.catalog import client_for
from agent_factory.step.client import Client
from agent_factory.step.contract import Step, StepResult


async def run(step: Step, observer: Observer, client: Client | None = None) -> StepResult:
    """Run one llm step to its end: send it, show the answer to the observer,
    and either return the result or raise the `JobFailed` subclass that says
    why there is none."""
    client = client or client_for(step.provider)
    if not step.model:
        step = step.model_copy(update={"model": client.default_model})
    started = monotonic()
    try:
        answer = await asyncio.wait_for(client.complete(step), timeout=step.timeout_sec)
    except TimeoutError:
        raise TimedOut(f"exceeded {step.timeout_sec}s") from None
    at = datetime.now(tz=UTC)
    await observer.on_event(
        Event(kind=EventKind.AI, at=at, content=answer.text, usage=answer.tokens)
    )
    output = _parse_object(answer.text)  # after the ai event, so a bad answer is still logged
    await observer.on_event(Event(kind=EventKind.FINISHED, at=at, usage=answer.tokens))
    return StepResult(
        output=output,
        model=step.model,
        tokens=answer.tokens,
        duration_sec=monotonic() - started,
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
