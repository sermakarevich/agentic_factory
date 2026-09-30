import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from agent_factory.failure import JobFailed
from agent_factory.observe.log import LogObserver, configure_logging
from agent_factory.step.catalog import client_for
from agent_factory.step.contract import Reasoning, Step
from agent_factory.step.engine import run

log = logging.getLogger("agent_factory.step")


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


def load_schema(text: str) -> dict[str, Any]:
    if text.startswith("@"):
        text = Path(text[1:]).read_text()
    schema: dict[str, Any] = json.loads(text)
    return schema


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    logging.getLogger("httpx2").setLevel(logging.WARNING)  # one line per request otherwise
    given = {k: v for k, v in vars(args).items() if v is not None and k not in ("json", "debug")}
    given["output_schema"] = load_schema(given.pop("schema"))
    step = Step.model_validate(given)
    client = client_for(step.provider)
    log.info("step      %s %s", step.provider, step.model or client.default_model)
    try:
        result = asyncio.run(run(step, LogObserver(as_json=args.json), client))
    except JobFailed as failure:
        log.error("failed    %s: %s", type(failure).__name__, failure)
        return 1
    log.info("result    %s", result.model_dump_json())
    print(json.dumps(result.output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
