import json
import shlex
from string import Template

from agentic_factory.job.structured_output.contract import Schema

INSTRUCTION = Template(
    """Before your final message, submit the structured output of this job: JSON matching \
the schema below, given on stdin to this shell command:

$command <<'JSON'
{ ... }
JSON

It prints `ok`, or `invalid:` and every error with its path. Fix the JSON and run the \
command again until it prints `ok`; the last submission that printed `ok` counts. Then \
end your work as you were asked to.

The JSON Schema:
$schema"""
)


def wrap_prompt(prompt: str, schema: Schema, command: str) -> str:
    """The prompt the workflow gives the job: the job's own, then the request
    to submit the structured output with `command`, and the full schema as
    indented JSON, `$defs` included, so nested shapes are visible. The engine
    adds the summary request after it."""
    schema_text = json.dumps(schema, indent=2)
    return f"{prompt}\n\n{INSTRUCTION.substitute(command=command, schema=schema_text)}"


def command_prefix(af: str) -> str:
    """`af output submit`, with the given `af` executable: what a coder's tool rule allows."""
    return f"{shlex.quote(af)} output submit"


def submit_command(af: str, session_id: str) -> str:
    """`af output submit <session-id>`: the command the coder submits with."""
    return f"{command_prefix(af)} {shlex.quote(session_id)}"
