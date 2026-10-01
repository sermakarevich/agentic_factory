import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from options import given_options

from agentic_factory.callback import Callback
from agentic_factory.callbacks.json_lines import JsonLinesCallback
from agentic_factory.callbacks.log import LogCallback
from agentic_factory.failure import JobFailed
from agentic_factory.logging_setup import configure_logging
from agentic_factory.step.judge.catalog import judge_for
from agentic_factory.step.judge.client import JudgeClient
from agentic_factory.step.judge.contract import Judgment
from agentic_factory.step.judge.defaults import with_default_model
from agentic_factory.step.judge.engine import run

log = logging.getLogger("agentic_factory.judge")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Options left out are not passed on, so `Judgment` keeps its own defaults."""
    p = argparse.ArgumentParser(description="Run one judge step and watch its events.")
    p.add_argument("state", help="The text under judgment, or @file.")
    p.add_argument(
        "--questions",
        required=True,
        help='JSON of name to question, e.g. {"tone": {"kind": "choice", ...}}, or @file.',
    )
    p.add_argument("--provider", help="Default: settings.")
    p.add_argument("--model", help="Default: the judge's default model.")
    p.add_argument("--timeout", type=int, dest="timeout_sec", help="Seconds.")
    p.add_argument("--json", action="store_true", help="Events as JSON lines.")
    p.add_argument("--debug", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    _quiet_http_logs()
    judgment = _judgment_from_args(args)
    client = judge_for(judgment.provider)
    judgment = with_default_model(judgment, client)
    log.info("judge     %s %s", judgment.provider, judgment.model)
    return _run_and_print(judgment, client, _callback(args.json))


def _quiet_http_logs() -> None:
    logging.getLogger("httpx2").setLevel(logging.WARNING)  # one line per request otherwise


def _judgment_from_args(args: argparse.Namespace) -> Judgment:
    """The judgment as given; its questions loaded, everything left out a settings default."""
    given = given_options(args)
    given["state"] = _text_or_file(given["state"])
    given["questions"] = json.loads(_text_or_file(given["questions"]))
    return Judgment.model_validate(given)


def _text_or_file(option: str) -> str:
    return Path(option[1:]).read_text() if option.startswith("@") else option


def _callback(as_json: bool) -> Callback:
    return JsonLinesCallback() if as_json else LogCallback()


def _run_and_print(judgment: Judgment, client: JudgeClient, callback: Callback) -> int:
    """The engine run, its result logged and its answers printed; the exit code."""
    try:
        result = asyncio.run(run(judgment, callback, client))
    except JobFailed as failure:
        log.error("failed    %s: %s", type(failure).__name__, failure)
        return 1
    log.info("result    %s", result.model_dump_json())
    answers: dict[str, Any] = result.model_dump(mode="json")["answers"]
    print(json.dumps(answers, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
