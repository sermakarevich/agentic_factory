from string import Template

from agentic_factory.job.contract import Job

REMINDER = Template(
    "You did not submit the structured output of this job. Run `$command` now, with the "
    "JSON on stdin as you were told, until it prints `ok`. Then stop."
)


def reminder_job(asked: Job, command: str, number: int, tries_per_job: int) -> Job:
    """Reminder `number` (from 1) to submit, as a follow-up job: the asked job
    in its own session, with the reminder for its prompt, its tries stored
    after those of every job before it (each has at most `tries_per_job`)."""
    return asked.model_copy(
        update={
            "name": f"{asked.name}/reminder" if asked.name else "reminder",
            "prompt": REMINDER.substitute(command=command),
            "try_offset": number * tries_per_job,
        }
    )
