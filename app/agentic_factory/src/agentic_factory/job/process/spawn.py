import asyncio
from asyncio.subprocess import DEVNULL, PIPE, Process
from typing import Any

from agentic_factory.failure import CoderNotFound
from agentic_factory.job.process.environment import environment


async def start_process(argv: list[str], workdir: str, **options: Any) -> Process:
    """A coder command in the workdir: stdin closed (claude waits for piped
    input when it is open), stderr piped, stdout piped unless `options` say
    otherwise, leading its own process group so that `kill_process` reaches
    its children too. `options` go to `create_subprocess_exec` as given.
    `CoderNotFound` when the command is not installed."""
    try:
        return await asyncio.create_subprocess_exec(
            *argv,
            cwd=workdir,
            env=environment(workdir),
            stdin=DEVNULL,
            start_new_session=True,
            **{"stdout": PIPE, "stderr": PIPE, **options},
        )
    except FileNotFoundError:
        raise CoderNotFound(f"{argv[0]} is not installed") from None
