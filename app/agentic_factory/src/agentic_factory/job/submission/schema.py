from typing import Any

from agentic_factory.job.report.contract import JobReport
from agentic_factory.job.submission.contract import Schema

REPORT_KEY = "report"  # the submission's part with the coder's report
OUTPUT_KEY = "output"  # its part with the output the job asked for
DEFS_KEY = "$defs"  # where a JSON schema keeps the shapes its `$ref`s name


class ClashingDefs(ValueError):
    """The report's and the output's schema define one name differently."""


def submission_schema(output_schema: Schema | None) -> Schema:
    """What the coder submits: an object with a required `report` and, when
    the job has an output schema, a required `output` matching it. The
    `$defs` of both parts move to the top, where their `#/$defs/...` refs
    resolve. Raises `ClashingDefs` when both define a name differently."""
    report = JobReport.model_json_schema()
    parts: dict[str, Schema] = {REPORT_KEY: report}
    if output_schema is not None:
        parts[OUTPUT_KEY] = output_schema
    defs = merged_defs(list(parts.values()))
    schema: Schema = {
        "type": "object",
        "properties": {key: without_defs(part) for key, part in parts.items()},
        "required": list(parts),
        "additionalProperties": False,
    }
    if defs:
        schema[DEFS_KEY] = defs
    return schema


def asks_for_output(schema: Schema) -> bool:
    """Whether a submission schema has the output part."""
    return OUTPUT_KEY in schema.get("properties", {})


def merged_defs(parts: list[Schema]) -> dict[str, Any]:
    """The `$defs` of every part in one mapping."""
    merged: dict[str, Any] = {}
    for part in parts:
        for name, shape in part.get(DEFS_KEY, {}).items():
            if name in merged and merged[name] != shape:
                raise ClashingDefs(f"two different shapes are named {name}")
            merged[name] = shape
    return merged


def without_defs(part: Schema) -> Schema:
    return {key: value for key, value in part.items() if key != DEFS_KEY}
