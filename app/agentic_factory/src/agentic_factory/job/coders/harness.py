from abc import ABC, abstractmethod
from datetime import datetime
from typing import ClassVar

from agentic_factory.event import Event
from agentic_factory.job.contract import Job
from agentic_factory.tokens import Usage


class Harness(ABC):
    """One instance per run: it keeps the session id and running totals.

    Sync on purpose: every method is pure translation; none starts a process.
    """

    default_model: ClassVar[str] = ""
    compacts_while_running: ClassVar[bool] = False
    """True when `compact_command` may run beside a live session (the coder
    queues it for its next step). False means the coder compacts by itself
    at the threshold `command` passed on, and the command is for resumes only."""

    @abstractmethod
    def command(self, job: Job) -> list[str]:
        """Command line that starts the coder, including model, tools and session."""

    def new_session_command(self, workdir: str) -> list[str]:
        """Command that creates an empty session in `workdir` and prints it for
        `parse_session`. Empty when the coder accepts any id we choose: the
        engine then makes a uuid, and `command` passes it on every try."""
        return []

    def parse_session(self, stdout: str) -> str:
        """The id of the session `new_session_command` printed. Raises
        `ValueError` when the output does not name one."""
        raise NotImplementedError(f"{type(self).__name__} names no sessions")

    def tools_with_command(self, tools: list[str], command: str) -> list[str]:
        """The job's tools with one shell command, and any arguments after it,
        allowed too. The default leaves them as they are: an empty list
        already allows everything, and a coder that enforces no allow-list
        runs any command."""
        return tools

    @abstractmethod
    def compact_command(self, session_id: str) -> list[str]:
        """Command line that asks the coder to summarize this session's context."""

    @abstractmethod
    def parse_line(self, text: str) -> list[Event]:
        """One stdout line into zero or more events.

        Raises a `JobFailed` subclass when the line says the coder cannot
        continue, for example the context window is exhausted. The last
        event of a normal run is `finished` with the totals; a stream that
        ends without it means the coder died.
        """

    def usage_command(self, session_id: str) -> list[str]:
        """Command that prints the coder's own record of the session, with
        each model turn's usage, for `parse_usage`. Empty when the coder
        keeps none (its stream is then the only source of the totals)."""
        return []

    def parse_usage(self, stdout: str, since: datetime) -> Usage:
        """The usage of the turns made at or after `since`, summed, from what
        `usage_command` printed. Raises `ValueError` when the output is not
        that record."""
        raise NotImplementedError(f"{type(self).__name__} keeps no usage record")

    def end_of_stream(self) -> list[Event]:
        """Called once stdout closed: whatever the stream left unsaid.

        Coders may drop their last line on exit; a harness that buffered a turn
        emits it here, and a `finished` with the totals it has.
        """
        return []
