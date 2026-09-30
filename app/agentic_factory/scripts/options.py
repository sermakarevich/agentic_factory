from argparse import Namespace
from typing import Any

OUTPUT_FLAGS = ("json", "debug")  # how to show the run; not fields of the job or step


def given_options(args: Namespace) -> dict[str, Any]:
    """The options given on the command line, so the ones left out keep the
    defaults of settings.toml."""
    return {k: v for k, v in vars(args).items() if v is not None and k not in OUTPUT_FLAGS}
