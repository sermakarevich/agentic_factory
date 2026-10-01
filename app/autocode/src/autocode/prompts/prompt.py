"""Every autocode prompt: one template per job, one function collecting the variables."""

from collections.abc import Iterable, Sequence
from pathlib import Path
from string import Template

from autocode.contract import Finding, Ran, Unit
from autocode.run import E2E, FAILURES, Autocode

FOLDER = Path(__file__).parent
RULES = "rules"  # the template pasted into every other one


def prompt(
    name: str,
    run: Autocode,
    unit: Unit | None = None,
    failing: Sequence[Ran] = (),
    findings: Sequence[Finding] = (),
    problems: Sequence[str] = (),
) -> str:
    """The template `name` (a job: requirements, failures, baseline,
    scaffold, tests, e2e, implement, implement_fix, align, review,
    review_fix, gate_fix, resubmit) filled for this run, with the unit, the
    failing runs, the review's findings and the output's problems where the
    job has them."""
    return _rendered(name, values(run, unit, failing, findings, problems))


def values(
    run: Autocode,
    unit: Unit | None = None,
    failing: Sequence[Ran] = (),
    findings: Sequence[Finding] = (),
    problems: Sequence[str] = (),
) -> dict[str, object]:
    """Every variable any template names. Paths are relative to the repo
    root, the jobs' working folder."""
    common: dict[str, object] = {
        "repo": run.request.repo,
        "branch": run.branch,
        "feature": run.feature,
        "tests_dir": run.tests_dir,
    }
    return {
        **common,
        "rules": _rendered(RULES, common),
        "spec": _spec(run),
        "requirements_path": run.requirements_path,
        "failures_dir": f"{run.docs_dir}/{FAILURES}",
        "e2e_dir": run.tests_of(E2E),
        "units": _bullets(f"{item.id} {item.title}" for item in run.requirements.units),
        "test_command": run.commands.test,
        "unit_id": unit.id if unit else "",
        "unit_title": unit.title if unit else "",
        "after": ", ".join(unit.after) if unit and unit.after else "(none)",
        "failures_path": run.failures_path(unit.id) if unit else "",
        "unit_tests_dir": run.tests_of(unit.id) if unit else "",
        "unit_command": run.unit_check(unit.id).command if unit else "",
        "failing": "\n\n".join(_ran(item) for item in failing) or "(nothing)",
        "findings": _bullets(f"`{item.file}`: {item.problem} Fix: {item.fix}" for item in findings),
        "problems": _bullets(problems),
    }


def _spec(run: Autocode) -> str:
    """The spec where the job reads it: its file, or its text pasted in."""
    request = run.request
    if request.spec_is_file:
        return f"The feature's spec is the file `{request.spec.strip()}`; read it in full first."
    return f"The feature's spec:\n\n<spec>\n{request.spec.strip()}\n</spec>"


def _ran(item: Ran) -> str:
    """One failing run: its name, command, how it ended and its output's tail."""
    ended = "timed out" if item.timed_out else f"exited {item.exit_code}"
    return f"{item.name}: `{item.command}` {ended}, output's tail:\n\n```\n{item.tail}\n```"


def _bullets(lines: Iterable[str]) -> str:
    """One `- line` per line, or `- (none)`."""
    return "\n".join(f"- {line}" for line in lines) or "- (none)"


def _rendered(name: str, values: dict[str, object]) -> str:
    """The template `name.md` with `values` filled in."""
    text = (FOLDER / f"{name}.md").read_text(encoding="utf-8")
    return Template(text).substitute(values)
