from pathlib import Path
from typing import Any

from dynaconf import Dynaconf

from factory_settings.table import Table

ENV_PREFIX = (
    "AF"  # AF_STEP__MAX_TOKENS=4096 overrides [step] max_tokens in whichever package has it
)
SETTINGS_FILES = ["settings.toml", "settings.local.toml"]  # in the package's settings folder


def load[T: Table](model: type[T], folder: Path) -> T:
    """The package's settings.toml in `folder`, then its settings.local.toml
    over it, then the environment over both, as `model`."""
    return model.model_validate(_tables(_raw_values(folder)))


def _raw_values(folder: Path) -> dict[str, Any]:
    raw = Dynaconf(
        envvar_prefix=ENV_PREFIX,
        root_path=folder,
        settings_files=SETTINGS_FILES,
        load_dotenv=True,
        merge_enabled=True,
    )
    values: dict[str, Any] = raw.as_dict()
    return values


def _tables(values: dict[str, Any]) -> dict[str, Any]:
    """The tables only, named as the file names them: dynaconf upper-cases
    the keys and adds its own scalar options (`LOAD_DOTENV`)."""
    return {key.lower(): value for key, value in values.items() if isinstance(value, dict)}
