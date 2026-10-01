"""The Temporal side of a tick: spawns and status reads over real workflows."""

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from agentic_factory.job.contract import Job
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.structured_output.contract import Schema
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.poll import AlreadySpawned, UnknownWorkflow
from temporal_agentic_factory.workflows.job import search_attributes
from temporal_agentic_factory.workflows.job.workflow import JobWorkflow
from temporal_agentic_factory.workflows.structured_output.workflow import (
    JobWithStructuredOutputWorkflow,
    StructuredOutputJob,
)

STRUCTURED_TYPE = "job_with_structured_output"


class TemporalWorkflows:
    """`Workflows` over the configured server. One tick, one client."""

    async def spawn(self, workflow_id: str, job: Job, output_schema: Schema | None) -> str:
        """Start the job workflow, or the job with structured output when a schema
        is given; its id. Raises AlreadySpawned on conflict."""
        client = await connect()
        try:
            if output_schema is None:
                return await _started_job(client, workflow_id, job)
            return await _started_structured(client, workflow_id, job, output_schema)
        except WorkflowAlreadyStartedError as error:
            raise AlreadySpawned(workflow_id) from error

    async def status_of(self, workflow_id: str) -> str:
        """RUNNING, COMPLETED, ...; raises UnknownWorkflow when absent."""
        client = await connect()
        try:
            desc = await client.get_workflow_handle(workflow_id).describe()
        except RPCError as error:
            if error.status == RPCStatusCode.NOT_FOUND:
                raise UnknownWorkflow(workflow_id) from error
            raise
        name = getattr(desc.status, "name", None)
        return str(name or desc.status)

    async def outcome_of(self, workflow_id: str) -> JobOutcome:
        """The job outcome a completed workflow returned, read by its workflow type."""
        client = await connect()
        desc = await client.get_workflow_handle(workflow_id).describe()
        if desc.workflow_type != STRUCTURED_TYPE:
            return await client.get_workflow_handle_for(JobWorkflow.run, workflow_id).result()
        handle = client.get_workflow_handle_for(JobWithStructuredOutputWorkflow.run, workflow_id)
        return (await handle.result()).outcome

    async def exists(self, workflow_id: str) -> bool:
        """Whether this workflow resolves, whatever its status."""
        try:
            await self.status_of(workflow_id)
        except UnknownWorkflow:
            return False
        return True


async def _started_job(client: Client, workflow_id: str, job: Job) -> str:
    """The job workflow started; its id."""
    handle = await client.start_workflow(
        JobWorkflow.run,
        job,
        id=workflow_id,
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(job, job.name),
        static_summary=job.name,
    )
    return handle.id


async def _started_structured(
    client: Client, workflow_id: str, job: Job, output_schema: Schema
) -> str:
    """The job-with-structured-output workflow started; its id."""
    handle = await client.start_workflow(
        JobWithStructuredOutputWorkflow.run,
        StructuredOutputJob(job=job, output_schema=output_schema),
        id=workflow_id,
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(job, job.name),
        static_summary=job.name,
    )
    return handle.id
