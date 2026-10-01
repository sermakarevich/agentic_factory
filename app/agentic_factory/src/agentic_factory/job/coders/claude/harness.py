from datetime import UTC, datetime
from typing import Any

from agentic_factory.event import Event, EventKind, ToolCall
from agentic_factory.failure import ProviderError, RateLimited
from agentic_factory.job.coders.claude.store import session_exists
from agentic_factory.job.coders.claude.stream import (
    Block,
    BlockType,
    Line,
    LineType,
    RateLimitInfo,
    RateLimitStatus,
    ResultSubtype,
    SystemSubtype,
    Usage,
)
from agentic_factory.job.coders.decode import decoded_line
from agentic_factory.job.coders.harness import Harness
from agentic_factory.job.contract import Job
from agentic_factory.settings.load import settings
from agentic_factory.tokens import Tokens


class ClaudeHarness(Harness):
    """claude writes one line per message, so nothing is buffered: an `assistant`
    line is one `ai` event, a `user` line is one `tool` event per result, and
    `result` is `finished` with the totals claude computed itself.

    One assistant message can arrive as several lines sharing its message id
    (a thinking line then a text line, or a text line then a tool_use line),
    each carrying the message's full usage. The events are kept one per line,
    but only the first line of each id keeps its usage: merging the lines
    would need buffering and change what downstream code sees, while the
    ledger only needs each message's tokens once. Later lines keep their
    text and tool calls with `usage=None`.

    Tool results do not repeat the tool name, so names are remembered from the
    `tool_use` block by id.
    """

    default_model = settings.harness.claude.default_model

    def __init__(self) -> None:
        self._session_id = ""
        self._tool_names: dict[str, str] = {}
        self._seen_message_ids: set[str] = set()
        self._last_at = datetime.now(tz=UTC)

    def command(self, job: Job) -> list[str]:
        """The prompt goes right after `-p`: `--allowedTools` is variadic and
        would swallow it."""
        argv = ["claude", "-p", job.prompt, "--verbose", "--output-format", "stream-json"]
        argv += ["--model", job.model]
        argv += _autocompact_args()
        argv += _session_args(job.session_id)
        argv += _tool_args(job.tools)
        return argv

    def tools_with_command(self, tools: list[str], command: str) -> list[str]:
        """`Bash(<command>:*)` added to a restricted list: claude's rule for one
        shell command with any arguments. An empty list allows everything."""
        if not tools:
            return tools
        return [*tools, f"Bash({command}:*)"]

    def compact_command(self, session_id: str) -> list[str]:
        """A run of its own that only compacts; ~12 s. Used before a resume, as
        `--autocompact` covers the running session."""
        return ["claude", "-p", "/compact", "--resume", session_id, "--output-format", "json"]

    def parse_line(self, text: str) -> list[Event]:
        if not text.strip():
            return []
        decoded = decoded_line(text, Line)
        if decoded is None:
            return [self._unknown_line(text, raw={})]
        line, raw = decoded
        self._last_at = line.at or self._last_at
        match line.type:
            case LineType.SYSTEM:
                events = self._parse_system(line, raw)
            case LineType.ASSISTANT:
                events = [self._parse_assistant(line, raw)]
            case LineType.USER:
                events = self._parse_user(line, raw)
            case LineType.RATE_LIMIT:
                events = [self._parse_rate_limit(line, raw)]
            case LineType.RESULT:
                events = [self._parse_result(line, raw)]
            case _:
                events = [self._unknown_line(text, raw)]
        return events

    def _parse_system(self, line: Line, raw: dict[str, Any]) -> list[Event]:
        if line.subtype != SystemSubtype.INIT or self._session_id:
            return []  # hook chatter, or a repeated init
        self._session_id = line.session_id
        return [self._event(EventKind.SESSION, raw)]

    def _parse_assistant(self, line: Line, raw: dict[str, Any]) -> Event:
        blocks = line.message.blocks
        calls = [b for b in blocks if b.type == BlockType.TOOL_USE]
        self._remember_tool_names(calls)
        return self._event(
            EventKind.AI,
            raw,
            content="".join(b.text for b in blocks if b.type == BlockType.TEXT),
            tool_calls=[ToolCall(id=c.id, name=c.name, args=c.input) for c in calls],
            usage=self._usage_first_time(line),
        )

    def _usage_first_time(self, line: Line) -> Tokens | None:
        """The line's tokens, or None when its message id was already counted."""
        if line.message.usage is None:
            return None
        message_id = line.message.id
        if not message_id:
            return _to_tokens(line.message.usage)
        if message_id in self._seen_message_ids:
            return None
        self._seen_message_ids.add(message_id)
        return _to_tokens(line.message.usage)

    def _remember_tool_names(self, calls: list[Block]) -> None:
        """Tool results carry only the call id; the name comes from here."""
        for call in calls:
            self._tool_names[call.id] = call.name

    def _parse_user(self, line: Line, raw: dict[str, Any]) -> list[Event]:
        results = [b for b in line.message.blocks if b.type == BlockType.TOOL_RESULT]
        return [self._tool_event(result, raw) for result in results]

    def _tool_event(self, result: Block, raw: dict[str, Any]) -> Event:
        return self._event(
            EventKind.TOOL,
            raw,
            content=result.result_text,
            tool_call_id=result.tool_use_id,
            name=self._tool_names.get(result.tool_use_id, ""),
            error=result.is_error,
        )

    def _parse_rate_limit(self, line: Line, raw: dict[str, Any]) -> Event:
        info = line.rate_limit_info
        resets_at = _reset_time(info)
        if info.status == RateLimitStatus.REJECTED:
            raise RateLimited(resets_at or self._last_at)
        return self._event(EventKind.RATE_LIMIT, raw, resets_at=resets_at)

    def _parse_result(self, line: Line, raw: dict[str, Any]) -> Event:
        if line.is_error or line.subtype != ResultSubtype.SUCCESS:
            clip = settings.job.error_clip_chars
            raise ProviderError(f"claude ended with {line.subtype}: {line.result[:clip]}")
        return self._event(
            EventKind.FINISHED,
            raw,
            usage=_to_tokens(line.usage),
            cost_usd=line.total_cost_usd,
        )

    def _unknown_line(self, text: str, raw: dict[str, Any]) -> Event:
        return self._event(EventKind.UNKNOWN, raw, content=text.rstrip("\n"))

    def _event(self, kind: EventKind, raw: dict[str, Any], **fields: Any) -> Event:
        return Event(kind=kind, at=self._last_at, session_id=self._session_id, raw=raw, **fields)


def _autocompact_args() -> list[str]:
    """Compact at the job's threshold, or at the least claude accepts."""
    least = settings.harness.claude.autocompact_min_tokens
    return ["--autocompact", str(max(settings.job.compact_at_tokens, least))]


def _session_args(session_id: str) -> list[str]:
    """The session id is ours (`new_session_command` is empty): `--session-id`
    starts it, `--resume` continues it, and claude's store says which applies."""
    if not session_id:
        return []
    flag = "--resume" if session_exists(session_id) else "--session-id"
    return [flag, session_id]


def _tool_args(tools: list[str]) -> list[str]:
    """With a list only those tools are allowed and the rest is denied. With
    none every permission is skipped, as a headless run has nobody to ask."""
    if tools:
        return ["--allowedTools", *tools]
    return ["--dangerously-skip-permissions"]


def _reset_time(info: RateLimitInfo) -> datetime | None:
    """When the limit lifts, from epoch seconds; None when claude did not say."""
    if info.resets_at is None:
        return None
    return datetime.fromtimestamp(info.resets_at, tz=UTC)


def _to_tokens(usage: Usage) -> Tokens:
    return Tokens(
        input=usage.input_tokens,
        output=usage.output_tokens,
        cache_read=usage.cache_read_input_tokens,
        cache_write=usage.cache_creation_input_tokens,
    )
