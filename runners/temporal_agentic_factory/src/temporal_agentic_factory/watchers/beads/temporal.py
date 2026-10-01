"""The Temporal side of a tick: spawns and status reads over real workflows."""

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from agentic_factory.job.contract import Job
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.submission.contract import Schema
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.poll import AlreadySpawned, UnknownWorkflow
from temporal_agentic_factory.workflows.job import search_attributes
from temporal_agentic_factory.workflows.job.workflow import JobRequest, JobWorkflow


class TemporalWorkflows:
    """`Workflows` over the configured server. One tick, one client."""

    async def spawn(self, workflow_id: str, job: Job, output_schema: Schema | None) -> str:
        """Start the job workflow, asked for a structured output when a schema
        is given; its id. Raises AlreadySpawned on conflict."""
        client = await connect()
        request = JobRequest(job=job, output_schema=output_schema)
        try:
            return await _started_job(client, workflow_id, request)
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
        """The job outcome a completed workflow returned."""
        client = await connect()
        return await client.get_workflow_handle_for(JobWorkflow.run, workflow_id).result()

    async def exists(self, workflow_id: str) -> bool:
        """Whether this workflow resolves, whatever its status."""
        try:
            await self.status_of(workflow_id)
        except UnknownWorkflow:
            return False
        return True


async def _started_job(client: Client, workflow_id: str, request: JobRequest) -> str:
    """The job workflow started; its id."""
    job = request.job
    handle = await client.start_workflow(
        JobWorkflow.run,
        request,
        id=workflow_id,
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(job, job.name),
        static_summary=job.name,
    )
    return handle.id
