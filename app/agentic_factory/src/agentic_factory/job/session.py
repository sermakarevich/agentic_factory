import asyncio
from asyncio.subprocess import DEVNULL, PIPE
from pathlib import Path
from uuid import uuid4

from agentic_factory.failure import CoderCrashed
from agentic_factory.job.catalog import harness_for
from agentic_factory.job.contract import Job
from agentic_factory.job.environment import environment
from agentic_factory.job.harness import Harness
from agentic_factory.settings.load import settings


async def create_session(job: Job, harness: Harness | None = None) -> str:
    """The session every try of the job will run in, made before the first try
    so that each try starts the coder the same way. A uuid when the coder takes
    our id (claude); otherwise the coder's `new_session_command` names one."""
    harness = harness or harness_for(job.provider)
    argv = harness.new_session_command(job.workdir)
    if not argv:
        return str(uuid4())
    Path(job.workdir).mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=job.workdir,
        env=environment(job.workdir),
        stdin=DEVNULL,
        stdout=PIPE,
        stderr=PIPE,
    )
    stdout, stderr = await proc.communicate()
    output = (stderr + stdout)[-settings.job.failure_tail_chars :].decode(errors="replace")
    if proc.returncode != 0:
        raise CoderCrashed(proc.returncode or 1, output)
    try:
        return harness.parse_session(stdout.decode(errors="replace"))
    except ValueError as err:
        raise CoderCrashed(0, f"could not create a session: {err}") from None
