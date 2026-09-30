from agent_factory.job.contract import Job

HEADER = (
    "Try {attempt}: an earlier try of this job was interrupted. The session keeps "
    "whatever that try did, so continue from there and do not redo finished work; "
    "if the session is empty, start. The original instructions follow.\n\n"
)


def continue_job(job: Job, attempt: int, session_tokens: int = 0) -> Job:
    """The job for a retry: the same job, in the same session, with a header that
    tells the coder it is continuing and the session's last known context size
    (so the engine knows whether to compact first). Try 1 is returned unchanged."""
    if attempt <= 1:
        return job
    return job.model_copy(
        update={
            "session_tokens": session_tokens,
            "prompt": HEADER.format(attempt=attempt) + job.prompt,
        }
    )
