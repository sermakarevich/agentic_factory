import argparse
import asyncio
import logging
import sys
from pathlib import Path

from agentic_factory.failure import JobFailed
from agentic_factory.job.catalog import harness_for
from agentic_factory.job.contract import Job
from agentic_factory.job.engine import run
from agentic_factory.observe.log import LogObserver, configure_logging

log = logging.getLogger("agentic_factory.job")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Options left out are not passed on, so `Job` keeps the defaults of settings.toml."""
    p = argparse.ArgumentParser(description="Run one llm job and watch its events.")
    p.add_argument("prompt")
    p.add_argument("--provider", help="claude | opencode. Default: settings.")
    p.add_argument("--model", help="Default: the harness's default model.")
    p.add_argument("--workdir", default=".", help="Directory the coder works in.")
    p.add_argument("--session", dest="session_id", help="Session id of an earlier try to continue.")
    p.add_argument("--timeout", type=int, dest="timeout_sec", help="Seconds.")
    p.add_argument(
        "--stall", type=int, dest="stall_sec", help="Seconds without output before kill."
    )
    p.add_argument("--context-limit", type=int, dest="context_limit_tokens", help="Tokens.")
    p.add_argument("--json", action="store_true", help="Events as JSON lines.")
    p.add_argument("--debug", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    given = {k: v for k, v in vars(args).items() if v is not None and k not in ("json", "debug")}
    given["workdir"] = str(Path(given["workdir"]).resolve())
    job = Job.model_validate(given)
    harness = harness_for(job.provider)
    log.info("job       %s %s in %s", job.provider, job.model or harness.default_model, job.workdir)
    try:
        result = asyncio.run(run(job, LogObserver(as_json=args.json), harness))
    except JobFailed as failure:
        log.error("failed    %s: %s", type(failure).__name__, failure)
        return 1
    log.info("result    %s", result.model_dump_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
