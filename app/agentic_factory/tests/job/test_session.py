import json
from uuid import UUID

import pytest

from agentic_factory.failure import CoderCrashed, SessionNotCreated
from agentic_factory.job.coders.opencode.harness import OpencodeHarness
from agentic_factory.job.contract import Job
from agentic_factory.job.session import create_session, start_session

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


class RowStore:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, str, str]] = []

    async def start_session(
        self, session_id: str, provider: str, model: str, workdir: str, prompt: str
    ) -> None:
        self.rows.append((session_id, provider, model, workdir, prompt))


async def test_start_session_writes_the_row_with_the_model_the_engine_will_run() -> None:
    store = RowStore()
    printed = json.dumps({"data": {"id": "ses_new", "title": ""}})
    harness = Scripted(f"echo '{printed}'")
    unnamed = JOB.model_copy(update={"model": ""})

    assert await start_session(store, unnamed, harness) == "ses_new"  # type: ignore[arg-type]
    assert store.rows == [("ses_new", "opencode", harness.default_model, "/tmp", "p")]
