from uuid import uuid4

from agentic_factory.failure import CoderCrashed, SessionNotCreated
from agentic_factory.job.coders.harness import Harness
from agentic_factory.job.contract import Job
from agentic_factory.job.process.spawn import start_process
from agentic_factory.job.process.tail import tail_of
from agentic_factory.job.process.workdir import ensure_workdir


async def create_session(job: Job, harness: Harness) -> str:
    """The session every try of the job will run in, made before the first try
    so that each try starts the coder the same way. A uuid when the coder takes
    our id (claude); otherwise the coder's `new_session_command` names one."""
    argv = harness.new_session_command(job.workdir)
    if not argv:
        return str(uuid4())
    ensure_workdir(job)  # the command runs in it, before the engine makes it
    output = await _stdout_of(argv, job.workdir)
    return _session_named_in(output, harness)


async def _stdout_of(argv: list[str], workdir: str) -> str:
    """The command's stdout; `CoderCrashed` with the tail of its output when it fails."""
    proc = await start_process(argv, workdir)
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise CoderCrashed(proc.returncode or 1, tail_of(stderr + stdout))
    return stdout.decode(errors="replace")


def _session_named_in(output: str, harness: Harness) -> str:
    try:
        return harness.parse_session(output)
    except ValueError as err:
        raise SessionNotCreated(f"could not create a session: {err}") from None
