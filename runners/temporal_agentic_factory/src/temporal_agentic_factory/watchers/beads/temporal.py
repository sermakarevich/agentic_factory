"""The Temporal side of a tick: spawns and status reads over real workflows."""

from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from agentic_factory.job.contract import Job
from agentic_factory.job.outcome import JobOutcome
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.mapping import workflow_id
from temporal_agentic_factory.watchers.beads.poll import AlreadySpawned, UnknownWorkflow
from temporal_agentic_factory.workflows.job import search_attributes
from temporal_agentic_factory.workflows.job.workflow import JobWorkflow


class TemporalWorkflows:
    """`Workflows` over the configured server. One tick, one client."""

    async def spawn(self, bead_id: str, job: Job) -> str:
        """Start the bead's job workflow; its id. Raises AlreadySpawned on conflict."""
        client = await connect()
        wid = workflow_id(bead_id)
        try:
            handle = await client.start_workflow(
                JobWorkflow.run,
                job,
                id=wid,
                task_queue=settings.temporal.task_queue,
                search_attributes=search_attributes.at_start(job, job.name),
                static_summary=job.name,
            )
        except WorkflowAlreadyStartedError as error:
            raise AlreadySpawned(wid) from error
        return handle.id

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

    async def result_text(self, workflow_id: str) -> str:
        """One line on the finished job for the bead comment."""
        client = await connect()
        handle = client.get_workflow_handle(workflow_id, result_type=JobOutcome)
        outcome = await handle.result()
        if outcome.result is None:
            return f"failed: {outcome.failure}"
        verdict = outcome.report.verdict.value if outcome.report else "no report"
        return f"session {outcome.session_id}, verdict {verdict}"

    async def exists(self, bead_id: str) -> bool:
        """Whether this bead's workflow resolves, whatever its status."""
        try:
            await self.status_of(workflow_id(bead_id))
        except UnknownWorkflow:
            return False
        return True
