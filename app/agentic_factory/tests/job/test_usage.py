from datetime import UTC, datetime

import pytest

from agentic_factory.job.coders.opencode.harness import OpencodeHarness
from agentic_factory.job.contract import Job
from agentic_factory.job.usage import recover_usage
from agentic_factory.settings.load import settings
from agentic_factory.tokens import Usage


class SlowRecord(OpencodeHarness):
    def usage_command(self, session_id: str) -> list[str]:
        return ["sh", "-c", "sleep 3"]


class NoRecord(OpencodeHarness):
    def usage_command(self, session_id: str) -> list[str]:
        return []


class EmptyRecord(OpencodeHarness):
    def usage_command(self, session_id: str) -> list[str]:
        return ["sh", "-c", "echo '{\"data\": []}'"]


def job(tmp_path: object) -> Job:
    return Job(provider="opencode", model="m", prompt="p", workdir=str(tmp_path), session_id="s")


async def test_a_read_back_that_takes_too_long_is_given_up(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.job, "usage_wait_sec", 1)
    assert await recover_usage(SlowRecord(), job(tmp_path), datetime.now(UTC)) is None


async def test_a_coder_without_a_record_gives_nothing(tmp_path: object) -> None:
    assert await recover_usage(NoRecord(), job(tmp_path), datetime.now(UTC)) is None


async def test_a_record_without_turns_is_zero_usage(tmp_path: object) -> None:
    assert await recover_usage(EmptyRecord(), job(tmp_path), datetime.now(UTC)) == Usage()
