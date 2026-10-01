"""The digest job: every wiki page's one-sentence line and key points, verbatim."""

from distill.contract import DistillRequest, EntryPlan, FetchedSource


def digest_prompt(request: DistillRequest, fetched: FetchedSource, plan: EntryPlan) -> str:
    """The prompt; a clone's closing section traces the system, a text's the argument."""
    closing = "The system in five moves" if fetched.kind == "repo" else "The argument in five moves"
    return f"""\
You are writing the digest for "{fetched.title}" ({request.url}).

Run work dir (absolute): {fetched.work_dir}

1. Read ONLY {plan.research_dir}/wiki/*.md (never the source, the chunk files, or the web).

2. Write {plan.research_dir}/digest.md:
   - Backlink line: > [[index|Wiki]] | [[summary|Summary]]
   - Heading: # {fetched.title} — Digest
   - Then one section per wiki page in order: ## N. [[wiki/NN-x|Title]] with that page's
     **In one sentence:** line and its ## Key points bullets copied VERBATIM (no
     rewording, no merging).
   - End with ## {closing} (5–7 numbered clauses tracing the whole
     source's arc across the pages).

Do not run git.
"""
