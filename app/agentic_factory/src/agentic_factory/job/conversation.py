import json

from factory_store.store import StoredEvent

from agentic_factory.event import Event, EventKind
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
    """One event as a line; the kind picks the shape."""
    if event.kind == EventKind.SESSION:
        text = f"session {event.session_id}"
    elif event.kind == EventKind.AI:
        head = f"assistant: {event.content}" if event.content else "assistant:"
        lines = [head]
        limit = settings.conversation.tool_args_chars
        for call in event.tool_calls:
            args = json.dumps(call.args, sort_keys=True)
            if len(args) > limit:
                args = args[:limit] + CUT.strip()
            lines.append(f"  -> {call.name}({args})")
        text = "\n".join(lines)
    elif event.kind == EventKind.TOOL:
        output = clip_middle(event.content, settings.conversation.tool_output_chars)
        marker = " (error)" if event.error else ""
        text = f"tool {event.name}{marker}: {output}"
    elif event.kind == EventKind.RATE_LIMIT:
        resets = event.resets_at.isoformat() if event.resets_at is not None else "?"
        text = f"rate limit until {resets}"
    elif event.kind == EventKind.FINISHED:
        usage = f"in={event.usage.input} out={event.usage.output}" if event.usage else "no usage"
        text = f"finished: {usage}, cost ${event.cost_usd:.4f}"
    elif event.kind == EventKind.COMPACTION:
        text = f"compaction: {event.content}"
    else:
        text = f"unknown: {event.content}"
    return text


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
