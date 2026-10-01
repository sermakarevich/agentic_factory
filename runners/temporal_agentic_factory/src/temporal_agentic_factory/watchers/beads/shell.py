"""Subprocess calls to `bd`, with timeouts and clean errors.

Every call runs with the database's home as its cwd: that alone picks the
database, so `BEADS_DIR` is dropped from the child's environment.
"""

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

BD_BIN = "BD_BIN"
BEADS_DIR = "BEADS_DIR"

Run = Callable[[list[str], Path, int], str]
"""`bd <args>` in a cwd within a timeout: its stdout. `run_bd` for real, a fake in tests."""


class BeadsError(RuntimeError):
    """A failed beads call: the command, its stderr, and its return code."""


def bd_bin() -> str:
    """Absolute path to `bd`: env override, PATH, then ~/.local/bin."""
    override = os.environ.get(BD_BIN)
    if override and Path(override).is_file():
        return override
    found = shutil.which("bd")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "bd"
    if fallback.is_file():
        return str(fallback)
    raise BeadsError(f"bd executable not found (set {BD_BIN} to its path)")


def run_bd(args: list[str], cwd: Path, timeout_sec: int) -> str:
    """`bd <args>` stdout, run in `cwd`; raises BeadsError on failure or timeout."""
    try:
        done = subprocess.run(
            [bd_bin(), *args],
            cwd=cwd,
            env=_without_beads_dir(os.environ),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_sec,
        )
    except FileNotFoundError as error:
        raise BeadsError(f"bd executable not found: {error}") from error
    except subprocess.TimeoutExpired as error:
        raise BeadsError(f"bd {' '.join(args)} timed out after {timeout_sec}s") from error
    if done.returncode != 0:
        raise BeadsError(
            f"bd {' '.join(args)} failed (rc={done.returncode}): {done.stderr.strip()}"
        )
    return done.stdout


def _without_beads_dir(env: Mapping[str, str]) -> dict[str, str]:
    """The environment minus `BEADS_DIR`, which would point `bd` past its cwd."""
    return {key: value for key, value in env.items() if key != BEADS_DIR}
