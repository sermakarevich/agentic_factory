from pathlib import Path

from dynaconf import Dynaconf

from temporal_agentic_factory.settings.model import Settings

ENV_PREFIX = "AF"  # AF_TEMPORAL__ADDRESS=... overrides [temporal] address
SETTINGS_FILES = ["settings.toml", "settings.local.toml"]


def load() -> Settings:
    raw = Dynaconf(
        envvar_prefix=ENV_PREFIX,
        root_path=Path(__file__).parent,
        settings_files=SETTINGS_FILES,
        load_dotenv=True,
        merge_enabled=True,
    )
    return Settings.model_validate({key.lower(): value for key, value in raw.as_dict().items()})


settings = load()
