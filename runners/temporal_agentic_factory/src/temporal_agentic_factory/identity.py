import os
import socket
import subprocess
from pathlib import Path


def runner_identity() -> str:
    """`host:pid:sha`, what Temporal shows as the worker of every task it ran: on the
    task queue's workers page, in `ActivityTaskStarted` events and the `Runner` column."""
    return f"{socket.gethostname()}:{os.getpid()}:{code_version()}"


def code_version() -> str:
    """The short git sha of the checkout the runner runs from; `unknown` outside one."""
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).parent,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return done.stdout.strip()
