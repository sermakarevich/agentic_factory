import asyncio
import contextlib
import os
import signal
from asyncio.subprocess import Process


async def kill_process(proc: Process, wait_sec: float) -> None:
    """Kill the process with everything it started (it leads its own process
    group, see `start_process`), then wait for it to be reaped, at most
    `wait_sec`. Nothing when it has already exited."""
    if proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(proc.wait(), wait_sec)
