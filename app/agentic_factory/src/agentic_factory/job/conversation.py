import json
from collections.abc import Callable

from factory_store.store import StoredEvent

from agentic_factory.event import Event, EventKind, ToolCall
from agentic_factory.settings.load import settings

TRY_HEADER = "===== try {attempt} ====="
CUT = " [...] "


def clip_middle(text: str, limit: int) -> str:
    """Keep the ends so a long output still shows what started and ended it."""
    if len(text) <= limit:
        return text
    if limit <= len(CUT):
        return text[:limit]
    remaining = limit - len(CUT)
    head_len = (remaining + 1) // 2
    tail_len = remaining // 2
    return (
        text[:head_len] + CUT + text[len(text) - tail_len :] if tail_len else text[:head_len] + CUT
    )


def render_event(event: Event) -> str:
    """One event as a block; the kind picks the shape."""
    return RENDERERS.get(event.kind, _render_unknown)(event)


def _render_session(event: Event) -> str:
    return f"session {event.session_id}"


def _render_rate_limit(event: Event) -> str:
    resets = event.resets_at.isoformat() if event.resets_at is not None else "?"
    return f"rate limit warning (not blocking), resets {resets}"


def _render_compaction(event: Event) -> str:
    return f"compaction: {event.content}"


def _render_unknown(event: Event) -> str:
    return f"unknown: {event.content}"


def _render_ai(event: Event) -> str:
    """The assistant's text, then one line per tool it called."""
    head = f"assistant: {event.content}" if event.content else "assistant:"
    return "\n".join([head, *(_render_tool_call(call) for call in event.tool_calls)])


def _render_tool_call(call: ToolCall) -> str:
    args = json.dumps(call.args, sort_keys=True)
    limit = settings.conversation.tool_args_chars
    if len(args) > limit:
        args = args[:limit] + CUT.strip()
    return f"  -> {call.name}({args})"


def _render_tool(event: Event) -> str:
    output = clip_middle(event.content, settings.conversation.tool_output_chars)
    marker = " (error)" if event.error else ""
    return f"tool {event.name}{marker}: {output}"


def _render_finished(event: Event) -> str:
    usage = f"in={event.usage.input} out={event.usage.output}" if event.usage else "no usage"
    return f"finished: {usage}, cost ${event.cost_usd:.4f}"


RENDERERS: dict[EventKind, Callable[[Event], str]] = {
    EventKind.SESSION: _render_session,
    EventKind.AI: _render_ai,
    EventKind.TOOL: _render_tool,
    EventKind.RATE_LIMIT: _render_rate_limit,
    EventKind.FINISHED: _render_finished,
    EventKind.COMPACTION: _render_compaction,
}


def render(rows: list[StoredEvent]) -> str:
    """The session as a transcript, in stored order: a header when the try
    changes, then one block per event. Tool outputs and arguments are clipped
    so a long run still fits a model's context."""
    if not rows:
        return ""
    blocks: list[str] = []
    previous: int | None = None
    for row in rows:
        if row.attempt != previous:
            blocks.append(TRY_HEADER.format(attempt=row.attempt))
            previous = row.attempt
        blocks.append(render_event(Event.model_validate(row.payload)))
    return "\n".join(blocks)
