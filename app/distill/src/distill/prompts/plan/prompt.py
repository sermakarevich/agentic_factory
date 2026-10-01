"""The plan job: decide where the entry lives, lay the folder out, copy the
source in, and state the plan."""

from pathlib import Path

from distill import vault
from distill.contract import DistillRequest, FetchedSource
from distill.prompts.template import rendered
from distill.settings.load import settings


def plan_prompt(request: DistillRequest, fetched: FetchedSource, run_date: str) -> str:
    """The prompt, given the request, what fetch made, and the run date as YYYY-MM-DD."""
    folder = Path(__file__).parent
    text = rendered(folder, "plan", main_values(request, fetched, run_date))
    if fetched.kind == "repo":
        text += rendered(folder, "codebase_track", {})
    return text


def main_values(
    request: DistillRequest, fetched: FetchedSource, run_date: str
) -> dict[str, object]:
    """The template variables for the plan, with the folder section filled in."""
    return {
        "title": fetched.title,
        "url": request.url,
        "kind": fetched.kind,
        "work_dir": fetched.work_dir,
        "source_md": fetched.source_md,
        "folder_section": folder_text(request, fetched, run_date),
        "pdf_mb": pdf_limit(),
        "type": fetched.type,
    }


def folder_text(request: DistillRequest, fetched: FetchedSource, run_date: str) -> str:
    """Step 2: the entry folder, fixed by the request or derived by the job."""
    if request.target_dir:
        return fixed_folder(request, fetched)
    return derived_folder(request, fetched, run_date)


def fixed_folder(request: DistillRequest, fetched: FetchedSource) -> str:
    """The request names the folder: the job only checks what is already there."""
    return rendered(
        Path(__file__).parent,
        "folder_fixed",
        {
            "target_dir": request.target_dir,
            "url": request.url,
            "source_md": fetched.source_md,
        },
    )


def derived_folder(request: DistillRequest, fetched: FetchedSource, run_date: str) -> str:
    """No folder was named: the job routes by subject and provenance."""
    return rendered(
        Path(__file__).parent,
        "folder_derived",
        {
            "research": vault.research_dir(),
            "investment": vault.investment_dir(),
            "url": request.url,
            "source_md": fetched.source_md,
            "run_date": run_date,
        },
    )


def pdf_limit() -> str:
    """The PDF copy limit in MB, as the prompt names it."""
    return f"{settings.vault.pdf_copy_max_bytes / 1_000_000:g}"
