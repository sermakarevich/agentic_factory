import asyncio
import logging
from datetime import datetime

from agentic_factory.job.coders.harness import Harness
from agentic_factory.job.contract import Job
from agentic_factory.job.process.kill import kill_process
from agentic_factory.job.process.spawn import start_process
from agentic_factory.settings.load import settings
from agentic_factory.tokens import Usage

log = logging.getLogger("agentic_factory.job")


async def recover_usage(harness: Harness, job: Job, since: datetime) -> Usage | None:
    """The usage of the turns the coder made since `since`, read back from
    its own record of the session. For a run whose stream lost its totals
    (opencode drops its last line at exit). Best effort: None when the coder
    keeps no record, when the read-back fails or takes too long, or when its
    output is not the record; the run's result does not depend on it."""
    argv = harness.usage_command(job.session_id)
    if not argv:
        return None
    output = await _output_within_limit(argv, job.workdir)
    if output is None:
        return None
    try:
        return harness.parse_usage(output, since)
    except ValueError as err:
        log.warning("usage of %s not read back: %s", job.session_id, err)
        return None


async def _output_within_limit(argv: list[str], workdir: str) -> str | None:
    """The command's stdout, or None when it fails or overruns `usage_wait_sec`."""
    proc = await start_process(argv, workdir)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), settings.job.usage_wait_sec)
    except TimeoutError:
        await kill_process(proc, settings.job.exit_wait_sec)
        log.warning("usage read-back did not finish in %ss", settings.job.usage_wait_sec)
        return None
    if proc.returncode != 0:
        log.warning(
            "usage read-back exited %s: %s",
            proc.returncode,
            stderr.decode(errors="replace").strip(),
        )
        return None
    return stdout.decode(errors="replace")
