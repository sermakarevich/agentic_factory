import json
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from agent_factory.event import Event, EventKind, ToolCall
from agent_factory.failure import ProviderError, RateLimited
from agent_factory.job.claude.store import session_exists
from agent_factory.job.claude.stream import (
    Block,
    BlockType,
    Line,
    LineType,
    RateLimitStatus,
    ResultSubtype,
    SystemSubtype,
    Usage,
)
from agent_factory.job.contract import Job
from agent_factory.job.harness import Harness
from agent_factory.settings.load import settings
from agent_factory.tokens import Tokens


class ClaudeHarness(Harness):
    """claude writes one line per message, so nothing is buffered: an `assistant`
    line is one `ai` event, a `user` line is one `tool` event per result, and
    `result` is `finished` with the totals claude computed itself.

    Tool results do not repeat the tool name, so names are remembered from the
    `tool_use` block by id.
    """

    default_model = settings.harness.claude.default_model

    def __init__(self) -> None:
        self._session_id = ""
        self._tool_names: dict[str, str] = {}
        self._last_at = datetime.now(tz=UTC)

    def command(self, job: Job) -> list[str]:
        """The prompt goes right after `-p`: `--allowedTools` is variadic and
        would swallow it. With no tool list every permission is skipped, as a
        headless run has nobody to ask; with a list only those tools are allowed
        and the rest is denied. The session id is ours (`new_session_command`
        is empty): `--session-id` starts it, `--resume` continues it, and
        claude's store says which applies."""
        argv = ["claude", "-p", job.prompt, "--verbose", "--output-format", "stream-json"]
        argv += ["--model", job.model]
        least = settings.harness.claude.autocompact_min_tokens
        compact_at = max(settings.job.compact_at_tokens, least)
        argv += ["--autocompact", str(compact_at)]
        if job.session_id:
            flag = "--resume" if session_exists(job.session_id) else "--session-id"
            argv += [flag, job.session_id]
        if job.tools:
            argv += ["--allowedTools", *job.tools]
        else:
            argv.append("--dangerously-skip-permissions")
        return argv

    def compact_command(self, session_id: str) -> list[str]:
        """A run of its own that only compacts; ~12 s. Used before a resume, as
        `--autocompact` covers the running session."""
        return ["claude", "-p", "/compact", "--resume", session_id, "--output-format", "json"]

    def parse_line(self, text: str) -> list[Event]:
        if not text.strip():
            return []
        try:
            raw = json.loads(text)
            line = Line.model_validate(raw)
        except (ValueError, ValidationError):
            return [self._unknown_line(text, raw={})]
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
        for call in calls:
            self._tool_names[call.id] = call.name
        return self._event(
            EventKind.AI,
            raw,
            content="".join(b.text for b in blocks if b.type == BlockType.TEXT),
            tool_calls=[ToolCall(id=c.id, name=c.name, args=c.input) for c in calls],
            usage=_to_tokens(line.message.usage) if line.message.usage else None,
        )

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
        resets_at = (
            datetime.fromtimestamp(info.resets_at, tz=UTC) if info.resets_at is not None else None
        )
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
        return self._event(
            EventKind.UNKNOWN,
            raw if isinstance(raw, dict) else {},
            content=text.rstrip("\n"),
        )

    def _event(self, kind: EventKind, raw: dict[str, Any], **fields: Any) -> Event:
        return Event(kind=kind, at=self._last_at, session_id=self._session_id, raw=raw, **fields)


def _to_tokens(usage: Usage) -> Tokens:
    return Tokens(
        input=usage.input_tokens,
        output=usage.output_tokens,
        cache_read=usage.cache_read_input_tokens,
        cache_write=usage.cache_creation_input_tokens,
    )
