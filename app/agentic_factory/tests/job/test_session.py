import json
from uuid import UUID

import pytest

from agentic_factory.failure import CoderCrashed, SessionNotCreated
from agentic_factory.job.contract import Job
from agentic_factory.job.opencode.harness import OpencodeHarness
from agentic_factory.job.session import create_session

JOB = Job(provider="opencode", model="m", prompt="p", workdir="/tmp")


class Scripted(OpencodeHarness):
    """The real opencode parser; the creating process is a shell script."""

    def __init__(self, script: str) -> None:
        super().__init__()
        self.script = script

    def new_session_command(self, workdir: str) -> list[str]:
        return ["sh", "-c", self.script]


async def test_a_coder_that_takes_our_id_gets_a_uuid() -> None:
    class Named(Scripted):
        def new_session_command(self, workdir: str) -> list[str]:
            return []

    assert UUID(await create_session(JOB, Named("unused")))


async def test_the_coder_names_the_session_it_created() -> None:
    printed = json.dumps({"data": {"id": "ses_new", "title": ""}})
    assert await create_session(JOB, Scripted(f"echo '{printed}'")) == "ses_new"


async def test_failure_to_create_is_a_crash_with_the_output() -> None:
    with pytest.raises(CoderCrashed, match="boom"):
        await create_session(JOB, Scripted("echo boom >&2; exit 3"))
    error = json.dumps({"_tag": "InvalidRequestError", "message": "Expected a valid JSON body"})
    with pytest.raises(SessionNotCreated, match="Expected a valid JSON body"):  # exit 0, json
        await create_session(JOB, Scripted(f"echo '{error}'"))
