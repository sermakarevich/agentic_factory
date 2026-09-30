import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from agent_factory.event import Event, EventKind, ToolCall
from agent_factory.failure import ContextPressure, ProviderError
from agent_factory.job.contract import Job
from agent_factory.job.harness import Harness
from agent_factory.job.opencode.stream import Line, LineType, Reason, StepTokens, ToolStatus
from agent_factory.settings.load import settings
from agent_factory.tokens import Tokens


class Turn(BaseModel):
    """One model turn as it is being collected: text, the calls the model made,
    and the tool events for their outputs. Emitted when `step_finish` arrives."""

    text: list[str] = Field(default_factory=list)
    calls: list[ToolCall] = Field(default_factory=list)
    tools: list[Event] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.text and not self.calls


class Created(BaseModel):
    """What `session.create` prints: the new session under `data`."""

    class Session(BaseModel):
        id: str

    data: Session


class OpencodeHarness(Harness):
    """A turn is buffered and emitted as one `ai` event, followed by one `tool`
    event per tool call, when its `step_finish` arrives. Reason `stop` also
    emits `finished` with tokens and cost summed over turns.

    opencode sometimes exits before writing the last `step_finish` (seen on
    v2.0.12 with `--standalone`), so `end_of_stream()` flushes a buffered turn
    and emits `finished` from the totals seen so far.
    """

    default_model = settings.harness.opencode.default_model
    compacts_while_running = True  # the request is queued; the run applies it at its next step

    def __init__(self) -> None:
        self._session_id = ""
        self._total = Tokens()
        self._cost = 0.0
        self._turn = Turn()
        self._finished = False
        self._last_at = datetime.now(tz=UTC)

    def command(self, job: Job) -> list[str]:
        """`--standalone` is required: through the background service the final
        `step_finish` line is dropped (seen on v2.0.12), so the run never looks
        finished. `job.tools` is not enforced: opencode has no allow-list flag,
        `--auto` approves whatever its config permits."""
        argv = ["opencode", "run", "--standalone", "--auto", "--format", "json"]
        argv += ["--model", job.model]
        if job.session_id:
            argv += ["--session", job.session_id]
        return [*argv, job.prompt]

    def new_session_command(self, workdir: str) -> list[str]:
        """opencode names its sessions itself, so one is created through its API
        before the first try. Must run in the workdir: sessions are scoped by
        project. Errors come back as JSON on stdout with exit code 0."""
        return ["opencode", "api", "--standalone", "session.create", "-d", "{}"]

    def parse_session(self, stdout: str) -> str:
        try:
            return Created.model_validate_json(stdout).data.id
        except ValidationError:
            clip = settings.job.error_clip_chars
            raise ValueError(f"no session in: {stdout.strip()[:clip]}") from None

    def compact_command(self, session_id: str) -> list[str]:
        """Queues a compaction on the session's server; must run in the workdir,
        since opencode scopes sessions by project. Nothing is visible in the
        run's stream; the context shrinks at the next step."""
        argv = ["opencode", "api", "--standalone", "session.compact"]
        return [*argv, "--param", f"sessionID={session_id}", "-d", "{}"]

    def parse_line(self, text: str) -> list[Event]:
        if not text.strip():
            return []
        try:
            raw = json.loads(text)
            line = Line.model_validate(raw)
        except (ValueError, ValidationError):
            return [self._unknown_step(text, raw={})]  # not JSON, or not a line shape
        self._last_at = line.at
        match line.type:
            case LineType.STEP_START:
                return self._parse_step_start(line, raw)
            case LineType.TEXT:
                self._turn.text.append(line.part.text)
            case LineType.TOOL_USE:
                self._parse_tool_use(line, raw)
            case LineType.STEP_FINISH:
                return self._parse_step_finish(line, raw)
            case LineType.ERROR:
                raise ProviderError(str(line.error)[: settings.job.error_clip_chars])
            case _:
                return [self._unknown_step(text, raw)]
        return []

    def end_of_stream(self) -> list[Event]:
        if self._finished:
            return []  # the stream had its final step_finish; nothing was lost
        if not self._session_id:
            return []  # never started: no session, no finished; the engine reports a crash
        events = self._flush_turn(self._last_at, usage=None, raw={})
        events.append(self._finish(self._last_at, raw={}))
        return events

    def _parse_step_start(self, line: Line, raw: dict[str, Any]) -> list[Event]:
        if self._session_id:
            return []
        self._session_id = line.session_id
        return [Event(kind=EventKind.SESSION, at=line.at, session_id=self._session_id, raw=raw)]

    def _parse_tool_use(self, line: Line, raw: dict[str, Any]) -> None:
        part, state = line.part, line.part.state
        if state.status not in (ToolStatus.COMPLETED, ToolStatus.ERROR):
            return  # a later line for the same call carries the outcome
        self._turn.calls.append(ToolCall(id=part.id, name=part.tool, args=state.input))
        output = state.output if state.status == ToolStatus.COMPLETED else str(state.error or "")
        self._turn.tools.append(
            Event(
                kind=EventKind.TOOL,
                at=line.at,
                session_id=self._session_id,
                content=output,
                tool_call_id=part.id,
                name=part.tool,
                error=state.status == ToolStatus.ERROR,
                raw=raw,
            )
        )

    def _parse_step_finish(self, line: Line, raw: dict[str, Any]) -> list[Event]:
        part = line.part
        usage = _to_tokens(part.tokens)
        self._total = self._total + usage
        self._cost += part.cost
        if part.reason == Reason.LENGTH:
            raise ContextPressure("opencode stopped: output or context length reached")
        events = self._flush_turn(line.at, usage, raw)
        if part.reason == Reason.STOP:
            events.append(self._finish(line.at, raw))
        return events

    def _flush_turn(self, at: datetime, usage: Tokens | None, raw: dict[str, Any]) -> list[Event]:
        """Emit the collected turn as `ai` plus its `tool` events; start a new one."""
        if self._turn.is_empty:
            return []
        turn = Event(
            kind=EventKind.AI,
            at=at,
            session_id=self._session_id,
            content="".join(self._turn.text),
            tool_calls=self._turn.calls,
            usage=usage,
            raw=raw,
        )
        events = [turn, *self._turn.tools]
        self._turn = Turn()
        return events

    def _unknown_step(self, text: str, raw: dict[str, Any]) -> Event:
        """A line this harness has no rule for; kept so a stream can be debugged."""
        return Event(
            kind=EventKind.UNKNOWN,
            at=self._last_at,
            session_id=self._session_id,
            content=text.rstrip("\n"),
            raw=raw if isinstance(raw, dict) else {},
        )

    def _finish(self, at: datetime, raw: dict[str, Any]) -> Event:
        """Mark the run finished and build the `finished` event with the totals."""
        self._finished = True
        return Event(
            kind=EventKind.FINISHED,
            at=at,
            session_id=self._session_id,
            usage=self._total,
            cost_usd=self._cost,
            raw=raw,
        )


def _to_tokens(step: StepTokens) -> Tokens:
    return Tokens(
        input=step.input,
        output=step.output,
        cache_read=step.cache.read,
        cache_write=step.cache.write,
    )
