"""A job with a structured output run as a child workflow of the calling one."""

from temporalio import workflow
from temporalio.workflow import ParentClosePolicy

with workflow.unsafe.imports_passed_through():
    from temporalio.exceptions import ChildWorkflowError

    from agentic_factory.job.contract import Job
    from agentic_factory.job.structured_output.contract import Schema
    from temporal_agentic_factory.workflows.job import search_attributes
    from temporal_agentic_factory.workflows.job.child import child_id, raised_for
    from temporal_agentic_factory.workflows.structured_output.workflow import (
        JobWithStructuredOutput,
        JobWithStructuredOutputWorkflow,
        StructuredOutputJob,
    )


async def run_job_with_structured_output(job: Job, schema: Schema) -> JobWithStructuredOutput:
    """For any workflow with a job whose structured output it needs: the job
    workflow with a structured output as a child, waited for. A job that
    failed for good has nothing to extract, and an output the coder never
    stated cannot be made up: either raises its own typed error here, so the
    workflow stops where fleet stopped on a missing outputs file."""
    try:
        return await workflow.execute_child_workflow(
            JobWithStructuredOutputWorkflow.run,
            StructuredOutputJob(job=job, output_schema=schema),
            id=child_id(job.name),
            static_summary=job.name,
            search_attributes=search_attributes.at_start(job, job.name),
            parent_close_policy=ParentClosePolicy.REQUEST_CANCEL,
        )
    except ChildWorkflowError as error:
        raise raised_for(job, error) from error
