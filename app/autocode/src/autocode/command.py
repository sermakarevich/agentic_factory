"""Running one of the repo's own commands: its exit code and its output's tail."""

import asyncio
import contextlib
import os
import signal
from pathlib import Path

from autocode.contract import Ran

TIMED_OUT = -1  # the exit code of a command killed at its timeout


async def ran(name: str, command: str, cwd: Path, timeout_sec: float, tail_chars: int) -> Ran:
    """`command` run by the shell in `cwd`, stdout and stderr together. At
    `timeout_sec` its whole process group is killed and what it printed so
    far is kept."""
    process = await asyncio.create_subprocess_shell(
        command,
        cwd=cwd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    assert process.stdout is not None
    printed = bytearray()
    try:
        await asyncio.wait_for(_read_all(process.stdout, printed), timeout_sec)
        exit_code = await process.wait()
    except TimeoutError:
        _kill_group(process.pid)
        await process.wait()
        return Ran(
            name=name,
            command=command,
            exit_code=TIMED_OUT,
            timed_out=True,
            tail=_tail(printed, tail_chars),
        )
    return Ran(name=name, command=command, exit_code=exit_code, tail=_tail(printed, tail_chars))


async def _read_all(stream: asyncio.StreamReader, printed: bytearray) -> None:
    """Every chunk of `stream` added to `printed` as it comes, so a timeout keeps it."""
    while chunk := await stream.read(65536):
        printed.extend(chunk)


def _kill_group(pid: int) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pid, signal.SIGKILL)


def _tail(printed: bytearray, chars: int) -> str:
    return printed.decode("utf-8", errors="replace")[-chars:]
