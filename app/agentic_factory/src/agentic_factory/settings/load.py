from pathlib import Path
from typing import Any

from dynaconf import Dynaconf

from agentic_factory.settings.model import Settings

ENV_PREFIX = "AF"  # AF_STEP__MAX_TOKENS=4096 overrides [step] max_tokens
SETTINGS_FILES = ["settings.toml", "settings.local.toml"]


def load() -> Settings:
    return Settings.model_validate(_lowercase_keys(_raw_values()))


def _raw_values() -> dict[str, Any]:
    """settings.toml, then settings.local.toml over it, then the env vars over both."""
    raw = Dynaconf(
        envvar_prefix=ENV_PREFIX,
        root_path=Path(__file__).parent,
        settings_files=SETTINGS_FILES,
        load_dotenv=True,
        merge_enabled=True,
    )
    values: dict[str, Any] = raw.as_dict()
    return values


def _lowercase_keys(values: dict[str, Any]) -> dict[str, Any]:
    """dynaconf upper-cases the sections; the model names them as the file does."""
    return {key.lower(): value for key, value in values.items()}


settings = load()
