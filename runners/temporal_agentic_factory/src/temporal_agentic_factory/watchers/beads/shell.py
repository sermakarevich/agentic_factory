"""Subprocess calls to `fleet` and `bd`, with timeouts and clean errors.

`fleet ready --json` lists startable beads; `fleet bd ...` runs `bd` against
the centralized fleet database, so this module never resolves homes or repos.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


class BeadsError(RuntimeError):
    """A failed beads call: the command, its stderr, and its return code."""


def _binary(name: str, env_override: str | None = None) -> str:
    """Absolute path to `fleet` or `bd`: env override, PATH, then ~/.local/bin."""
    if env_override and Path(env_override).is_file():
        return env_override
    found = shutil.which(name)
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / name
    if fallback.is_file():
        return str(fallback)
    raise BeadsError(f"{name} executable not found (set FLEET_BIN / BD_BIN to its path)")


def fleet_bin() -> str:
    """Absolute path to the `fleet` binary."""
    return _binary("fleet", os.environ.get("FLEET_BIN"))


def run_fleet(args: list[str], timeout_sec: int) -> str:
    """`fleet <args>` stdout; raises BeadsError on failure or timeout."""
    try:
        done = subprocess.run(
            [fleet_bin(), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_sec,
        )
    except FileNotFoundError as error:
        raise BeadsError(f"fleet executable not found: {error}") from error
    except subprocess.TimeoutExpired as error:
        raise BeadsError(f"fleet {' '.join(args)} timed out after {timeout_sec}s") from error
    if done.returncode != 0:
        raise BeadsError(
            f"fleet {' '.join(args)} failed (rc={done.returncode}): {done.stderr.strip()}"
        )
    return done.stdout


def run_fleet_json(args: list[str], timeout_sec: int) -> Any:
    """`fleet <args> --json` parsed, without the optional `{"data": ...}` envelope."""
    raw = run_fleet([*args, "--json"] if "--json" not in args else args, timeout_sec)
    if not raw.strip():
        return []
    parsed: Any = json.loads(raw)
    if isinstance(parsed, dict) and "data" in parsed:
        return parsed["data"]
    return parsed
