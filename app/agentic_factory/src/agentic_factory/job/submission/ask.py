from factory_store.store import Store
from pydantic import BaseModel, Field

from agentic_factory.job.coders.harness import Harness
from agentic_factory.job.contract import Job
from agentic_factory.job.submission.contract import Schema
from agentic_factory.job.submission.prompt import command_prefix, submit_command, wrap_prompt


class AskedJob(BaseModel):
    """A job as the coder is asked it, and the command it submits with."""

    job: Job = Field(description="The prompt with the submit request, the command allowed.")
    command: str = Field(description="`af output submit <session-id>`, ready to run.")


async def ask_for_submission(
    store: Store, job: Job, schema: Schema, af: str, harness: Harness
) -> AskedJob:
    """The submission schema (`submission_schema`) saved under the job's
    session, which must exist already, and the job asked to submit with
    `af`. The caller picks the job's harness (`harness_for`)."""
    await store.save_output_schema(job.session_id, schema)
    return asked_job(job, schema, af, harness)


def asked_job(job: Job, schema: Schema, af: str, harness: Harness) -> AskedJob:
    """The job with the submit request in its prompt and, when it restricts
    its tools, the submit command allowed by its coder's rule."""
    command = submit_command(af, job.session_id)
    tools = harness.tools_with_command(job.tools, command_prefix(af))
    prompt = wrap_prompt(job.prompt, schema, command)
    return AskedJob(job=job.model_copy(update={"prompt": prompt, "tools": tools}), command=command)
