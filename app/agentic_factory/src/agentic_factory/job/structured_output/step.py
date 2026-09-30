import logging
from typing import Any

from agentic_factory.callback import Callback
from agentic_factory.job.report.conversation import clip_middle
from agentic_factory.job.structured_output.contract import Extraction, Schema
from agentic_factory.settings.load import settings
from agentic_factory.step import engine as steps
from agentic_factory.step.contract import Step
from agentic_factory.step.providers.client import Client

log = logging.getLogger("agentic_factory.job")

SYSTEM_PROMPT = (
    "You read text a coding agent wrote while doing a job, and pick out the values the "
    "job asked it to state, matching the schema. Copy values as the agent wrote them; do "
    "not invent, guess or complete them. When the text does not state a field, give "
    "structured_output as null and name every field it does not state in missing."
)


def prompt_for(text: str) -> str:
    """The step's prompt: the text clipped to `structured_output.max_chars`, the
    ends kept, because the structured output is asked for at the end."""
    return clip_middle(text, settings.structured_output.max_chars)


def extraction_schema(schema: Schema) -> Schema:
    """The step's output schema: the job's structured output or null, plus the
    fields not stated. Strict mode wants every field, so without the null
    branch a model that found nothing would fill the output in. The job
    schema's own `$defs` move to the top, where their refs resolve, and every
    object in it is made strict, so a hand-written schema works like a
    pydantic one."""
    inner = strict(schema)
    defs = inner.pop("$defs", {})
    top: Schema = {
        "type": "object",
        "properties": {
            "structured_output": {"anyOf": [inner, {"type": "null"}]},
            "missing": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["structured_output", "missing"],
        "additionalProperties": False,
    }
    if defs:
        top["$defs"] = defs
    return top


def strict(node: Any) -> Any:
    """A copy of the schema in the shape strict mode wants: every object
    names every property as required and allows no other. Optional fields
    are expressed as `anyOf` with null, not by leaving them out."""
    if isinstance(node, list):
        return [strict(item) for item in node]
    if not isinstance(node, dict):
        return node
    copy = {key: strict(value) for key, value in node.items()}
    if "properties" in copy:
        copy["required"] = list(copy["properties"])
        copy["additionalProperties"] = False
    return copy


async def extract(text: str, schema: Schema, client: Client) -> Extraction:
    """One model step over the text. Raises the step's `JobFailed` when the
    model could not answer; the caller decides what that means. `client` is
    the one for `settings.step.provider`, the step's provider."""
    step = _extraction_step(text, schema)
    found = (await steps.run(step, Callback(), client)).parse(Extraction)
    log.info(
        "structured output by %s: %s",
        step.provider,
        "stated" if found.structured_output else "not stated",
    )
    return found


def _extraction_step(text: str, schema: Schema) -> Step:
    return Step(
        prompt=prompt_for(text),
        output_schema=extraction_schema(schema),
        system_prompt=SYSTEM_PROMPT,
    )
