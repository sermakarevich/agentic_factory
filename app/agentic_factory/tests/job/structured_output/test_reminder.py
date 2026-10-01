from agentic_factory.job.contract import Job
from agentic_factory.job.structured_output.reminder import reminder_job


def test_the_reminder_runs_in_the_same_session_with_its_tries_after_the_earlier_ones() -> None:
    asked = Job(name="plan", prompt="long prompt", workdir="/w", session_id="s1", tools=["Read"])
    reminder = reminder_job(asked, "af output submit s1", 2, 5)
    assert reminder.session_id == "s1" and reminder.tools == ["Read"]
    assert reminder.try_offset == 10 and reminder.name == "plan/reminder"
    assert reminder.prompt.startswith("You did not submit the structured output")
    assert "`af output submit s1`" in reminder.prompt and reminder.prompt.endswith("Then stop.")
