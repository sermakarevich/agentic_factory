import os
import subprocess

# the command run directly, by its python or by `uv run`; not a shell line or prompt naming it
CODERS_COMMAND = r"^(\S*python\S* |uv run )?(\S*/)?(factory|af) coders( |$)"


def other_coders_pids() -> list[int]:
    """The pids of `factory coders` processes on this machine other than this
    one and the `uv run` that started it."""
    found = subprocess.run(
        ["pgrep", "-f", CODERS_COMMAND], capture_output=True, text=True, check=False
    )
    pids = [int(pid) for pid in found.stdout.split()]
    return others(pids, {os.getpid(), os.getppid()})


def others(pids: list[int], own: set[int]) -> list[int]:
    """`pids` without this process's own."""
    return [pid for pid in pids if pid not in own]
