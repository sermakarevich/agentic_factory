from pathlib import Path

from temporalio.testing import ActivityEnvironment

from temporal_agentic_factory.distill import verify as activity


async def test_verify_reports_the_entry_folder_problems(tmp_path: Path) -> None:
    problems = await ActivityEnvironment().run(activity.verify_entry, str(tmp_path))
    assert "verify: missing index.md" in problems
    assert "verify: wiki/ holds no pages" in problems
