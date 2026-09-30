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
from agentic_factory.step.contract import Step
from agentic_factory.step.defaults import with_default_model
from agentic_factory.step.engine import run
from agentic_factory.step.providers.catalog import client_for
from agentic_factory.step.providers.client import Client
from agentic_factory.step.reasoning import Reasoning

log = logging.getLogger("agentic_factory.step")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Options left out are not passed on, so `Step` keeps its own defaults."""
    p = argparse.ArgumentParser(description="Run one llm step and watch its events.")
    p.add_argument("prompt")
    p.add_argument("--schema", required=True, help="JSON schema of the answer, or @file.")
    p.add_argument("--provider", help="Default: settings.")
    p.add_argument("--model", help="Default: the provider's default model.")
    p.add_argument("--system-prompt", help="Standing instructions; role and rules.")
    p.add_argument("--reasoning", choices=[r.value for r in Reasoning])
    p.add_argument("--max-tokens", type=int)
    p.add_argument("--timeout", type=int, dest="timeout_sec", help="Seconds.")
    p.add_argument("--json", action="store_true", help="Events as JSON lines.")
    p.add_argument("--debug", action="store_true")
    return p.parse_args(argv)


def load_schema(option: str) -> dict[str, Any]:
    """The `--schema` option as a JSON schema: given inline, or as `@file`."""
    schema: dict[str, Any] = json.loads(_schema_text(option))
    return schema


def _schema_text(option: str) -> str:
    return Path(option[1:]).read_text() if option.startswith("@") else option


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    _quiet_http_logs()
    step = _step_from_args(args)
    client = client_for(step.provider)
    step = with_default_model(step, client)
    log.info("step      %s %s", step.provider, step.model)
    return _run_and_print(step, client, _callback(args.json))


def _quiet_http_logs() -> None:
    logging.getLogger("httpx2").setLevel(logging.WARNING)  # one line per request otherwise


def _step_from_args(args: argparse.Namespace) -> Step:
    """The step as given; its schema loaded, everything left out a settings default."""
    given = given_options(args)
    given["output_schema"] = load_schema(given.pop("schema"))
    return Step.model_validate(given)


def _callback(as_json: bool) -> Callback:
    return JsonLinesCallback() if as_json else LogCallback()


def _run_and_print(step: Step, client: Client, callback: Callback) -> int:
    """The engine run, its result logged and its output printed; the exit code."""
    try:
        result = asyncio.run(run(step, callback, client))
    except JobFailed as failure:
        log.error("failed    %s: %s", type(failure).__name__, failure)
        return 1
    log.info("result    %s", result.model_dump_json())
    print(json.dumps(result.output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
