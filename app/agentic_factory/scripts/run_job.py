import argparse
import asyncio
import logging
import sys
from pathlib import Path

from options import given_options

from agentic_factory.callbacks.json_lines import JsonLinesCallback
from agentic_factory.callbacks.log import LogCallback
from agentic_factory.failure import JobFailed
from agentic_factory.job.callback import JobCallback
from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.coders.harness import Harness
from agentic_factory.job.contract import Job
from agentic_factory.job.defaults import with_default_model
from agentic_factory.job.engine import run
from agentic_factory.job.summary.contract import JobSummary
from agentic_factory.job.summary.repair import repair_summary
from agentic_factory.logging_setup import configure_logging
from agentic_factory.settings.load import settings
from agentic_factory.step.providers.catalog import client_for

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
    p.add_argument("--json", action="store_true", help="Events as JSON lines on stdout.")
    p.add_argument("--debug", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    job = _job_from_args(args)
    harness = harness_for(job.provider)
    job = with_default_model(job, harness)
    log.info("job       %s %s in %s", job.provider, job.model, job.workdir)
    return _run_and_log(job, harness, _callback(args.json))


def _job_from_args(args: argparse.Namespace) -> Job:
    """The job as given; its workdir absolute, everything left out a settings default."""
    given = given_options(args)
    given["workdir"] = str(Path(given["workdir"]).resolve())
    return Job.model_validate(given)


def _callback(as_json: bool) -> JobCallback:
    return JsonLinesCallback() if as_json else LogCallback()


def _run_and_log(job: Job, harness: Harness, callback: JobCallback) -> int:
    """The engine run, with its result or failure logged; the exit code."""
    try:
        result = asyncio.run(run(job, callback, harness, _repair_summary_with_step_client))
    except JobFailed as failure:
        log.error("failed    %s: %s", type(failure).__name__, failure)
        return 1
    log.info("result    %s", result.model_dump_json())
    return 0


async def _repair_summary_with_step_client(block: str) -> JobSummary | None:
    """The engine's repair: the summary step with the client for the step
    provider from settings, made only when a summary needs repairing."""
    return await repair_summary(block, client_for(settings.step.provider))


if __name__ == "__main__":
    sys.exit(main())
