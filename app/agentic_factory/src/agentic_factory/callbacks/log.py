import json
import logging
import sys

from agentic_factory.callback import Callback, JobEnd
from agentic_factory.event import Event, EventKind, ToolCall
from agentic_factory.settings.load import settings
from agentic_factory.tokens import Tokens

log = logging.getLogger("agentic_factory.job")


class LogCallback(Callback):
    """Logs one line per event and one for the end of the run. Human layout
    by default, JSON lines with `as_json`."""

    def __init__(self, as_json: bool = False) -> None:
        self.as_json = as_json

    async def on_event(self, event: Event) -> None:
        level = logging.DEBUG if event.kind == EventKind.UNKNOWN else logging.INFO
        if self.as_json:
            log.log(level, event.model_dump_json(exclude={"raw"}))
        else:
            log.log(level, "%-9s %s", event.kind.value, _describe(event))

    async def on_end(self, end: JobEnd) -> None:
        if self.as_json:
            log.info(end.model_dump_json(exclude={"result"}))
        else:
            log.info("%-9s %s", "end", _describe_end(end))


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(message)s", "%H:%M:%S"))
    logging.basicConfig(level=level, handlers=[handler], force=True)


def _describe(event: Event) -> str:
    match event.kind:
        case EventKind.SESSION:
            return event.session_id
        case EventKind.AI:
            return _describe_ai(event)
        case EventKind.TOOL:
            return f"{event.name} -> {_clip(event.content)}"
        case EventKind.RATE_LIMIT:
            return f"resets_at={event.resets_at}"
        case EventKind.FINISHED:
            return f"{_tokens(event.usage)}  cost=${event.cost_usd:.4f}"
        case EventKind.COMPACTION | EventKind.UNKNOWN:
            return _clip(event.content)


def _describe_end(end: JobEnd) -> str:
    how = "done" if end.done else f"failed {end.failure!r}"
    return (
        f"{how} after {end.duration_sec:.1f}s  {end.stats.turns} turns  "
        f"{_tokens(end.tokens)}  cost=${end.cost_usd:.4f}"
    )


def _describe_ai(event: Event) -> str:
    parts = [_tokens(event.usage)]
    if event.content:
        parts.append(_clip(event.content))
    parts += [_tool_call_text(call) for call in event.tool_calls]
    return "  ".join(parts)


def _tool_call_text(call: ToolCall) -> str:
    return f"{call.name}({json.dumps(call.args)[: settings.log.content_width]})"


def _tokens(usage: Tokens | None) -> str:
    if usage is None:
        return "tokens=?"
    cache = (
        f" cache_r={usage.cache_read} cache_w={usage.cache_write}"
        if usage.cache_read or usage.cache_write
        else ""
    )
    return f"tokens in={usage.input} out={usage.output}{cache}"


def _clip(text: str) -> str:
    flat = " ".join(text.split())
    width = settings.log.content_width
    return repr(flat if len(flat) <= width else flat[: width - 1] + "…")
