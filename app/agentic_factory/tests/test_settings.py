import pytest

from agentic_factory.settings.load import load, settings


def test_toml_defaults_are_typed() -> None:
    assert settings.job.provider in ("opencode", "claude")
    assert settings.step.opencode.base_url.startswith("https://")


def test_env_overrides_a_nested_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AF_JOB__TIMEOUT_SEC", "5")
    assert load().job.timeout_sec == 5
    assert load().job.stall_sec == settings.job.stall_sec  # the rest is untouched


def test_every_knob_is_a_setting() -> None:
    assert settings.log.content_width > 0
    assert settings.job.failure_tail_chars > 0
    assert settings.harness.claude.autocompact_min_tokens >= 100_000
    assert settings.step.opencode.retry_after_default_sec > 0
    assert settings.conversation.tool_output_chars > 0
