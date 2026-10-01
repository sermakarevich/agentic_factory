from agentic_factory.job.contract import Job
from agentic_factory.job.report.contract import JobReport, Verdict


def failed_report(job: Job, failure: str) -> JobReport:
    """The report of a job the engine could not finish, written by code: no
    coder was left to submit one. Its task is the job's name, or else the
    first line of its prompt."""
    return JobReport(
        task=job.name or job.prompt.strip().split("\n", 1)[0],
        done=[],
        not_done=[],
        problems=[failure],
        verdict=Verdict.FAILED,
    )
