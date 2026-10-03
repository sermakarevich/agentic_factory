from pathlib import Path

import pytest
from factory_settings.load import load

import tutorial.settings.load
from tutorial.settings.load import settings
from tutorial.settings.model import Settings

FOLDER = Path(tutorial.settings.load.__file__).parent


def test_toml_defaults_are_typed() -> None:
    cfg = settings.tutorial
    assert cfg.root == "knowledge/tutorials"
    assert cfg.review_rounds == 2
    assert cfg.level in cfg.levels
    assert cfg.formats == ["md", "ipynb"]
    assert "nbconvert" in cfg.notebook_command


def test_the_rules_and_examples_are_vault_relative_paths() -> None:
    cfg = settings.tutorial
    assert cfg.rules == "skills/tutorial/rules.md"
    assert cfg.style_example == "knowledge/tutorials/grafana"
    assert isinstance(cfg.teaching_example, str)
    assert cfg.teaching_example.endswith("/evals_primer.ipynb")
    assert not any(
        path.startswith("/") for path in (cfg.rules, cfg.style_example, cfg.teaching_example)
    )


def test_env_overrides_a_nested_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AF_TUTORIAL__REVIEW_ROUNDS", "1")
    assert load(Settings, FOLDER).tutorial.review_rounds == 1
    assert load(Settings, FOLDER).tutorial.level == settings.tutorial.level


def test_every_role_has_a_coder_and_limits() -> None:
    for role in (settings.designer, settings.writer, settings.reviewer):
        assert role.provider
        assert role.timeout_sec > 0
        assert role.stall_sec > 0
    assert settings.tutorial.naming_timeout_sec > 0
    assert settings.tutorial.finish_timeout_sec > 0
