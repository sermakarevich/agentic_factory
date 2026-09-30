"""The plan job: decide where the entry lives, lay the folder out, copy the
source in, and state the plan."""

from summarise import vault
from summarise.contract import FetchedSource, SummariseRequest
from summarise.settings.load import settings


def plan_prompt(request: SummariseRequest, fetched: FetchedSource, run_date: str) -> str:
    """The prompt, given the request, what fetch made, and the run date as YYYY-MM-DD."""
    research = vault.research_dir()
    investment = vault.investment_dir()
    pdf_mb = settings.vault.pdf_copy_max_bytes / 1_000_000
    text = f"""\
You are planning where a fetched source will live in the knowledge base.

Source under study: "{fetched.title}" ({request.url}, kind {fetched.kind}).
Run work dir (absolute): {fetched.work_dir}

1. Read ONLY these two files (never the chunk bodies):
   - {fetched.source_md} (provenance header only: title, source, kind, fetched, tool)
   - {fetched.work_dir}/chunks.json (chunk index/slug/title list)
   Do not read {fetched.work_dir}/chunks/*.md: chunk bodies belong to later workers.

2. Decide the route from the title and chunk list:
   - Provenance-first rule (BEFORE deriving any folder name): search
     {research}/*/source/source.md and
     {investment}/*/source/source.md for a `Source:`
     line that equals this run's input ({request.url}, exact string match). If one
     exists, reuse that folder no matter what slug this run would have derived:
     refresh <research_dir>/source/source.md from {fetched.source_md}, state
     (step 5) that folder's absolute path and its existing folder basename as the
     slug, and continue. No question. Only when no such entry exists, derive a
     candidate folder below.
   - Investment/finance topic → base {investment} with a new
     folder <YYYY-MM-DD>-<PascalName>, using {run_date} for the date.
   - Anything else → {research}/<PascalName>.
   - If the route is genuinely unclear, ask with
     mcp__ask_human__ask_human_question. Never guess.
   - Folder-exists rule. If the candidate folder already exists, do NOT overwrite
     it and do NOT treat it as free; first check which case applies:
     1. Same source (re-run): read <candidate>/source/source.md and compare its
        `Source:` provenance url with this run's input ({request.url}). If they match,
        reuse the folder: refresh <research_dir>/source/source.md from {fetched.source_md},
        state the plan (step 5), and continue. No question.
     2. Genuine conflict: the provenance url differs, or source.md is missing or
        unreadable → ask with mcp__ask_human__ask_human_question, passing
        context=<this run's source url {request.url}>. Never guess,
        never overwrite an existing folder.
   - macOS rule: the filesystem is case-insensitive, so research/Livekit and
     research/LiveKit are the same folder. A candidate slug that differs only in
     case from an existing folder is case 2 above, not a new folder.
   - Epic-hub rule: a research/<Name>/ folder that contains a `sources/`
     subdirectory (plural) or whose index.md front-matter has
     `type: Research` is a research epic hub, not an entry. It is NEVER
     reusable as this run's folder, not even when the provenance search
     above found nothing (epic hubs carry no source/source.md, so that
     search never matches them). A candidate that collides with an epic hub,
     including a case-only collision per the macOS rule, is always case 2
     above: ask, never reuse, never write entry files into the hub.

3. Create the layout and copy the source:
   - mkdir -p <research_dir>/source <research_dir>/wiki/images
   - Copy {fetched.source_md} to <research_dir>/source/source.md.
   - If {fetched.work_dir}/source.pdf exists and is smaller than {pdf_mb:g} MB, copy it to
     <research_dir>/source/source.pdf too; otherwise pin the PDF location ({request.url}) at the
     top of <research_dir>/source/source.md.

4. Write <research_dir>/source/plan.md: a table mapping each chunk slug to its planned wiki
   page NN-<kebab-topic>.md plus a one-line "covers" note per row.

5. State the plan: research_dir (the absolute research dir), slug (the PascalName),
   title ("{fetched.title}") and type ("{fetched.type}").
   Type rule from the source kind ({fetched.kind}): youtube → Video, pdf → Paper,
   x/article → Article, repo → Codebase. This run: {fetched.type}.

Do not run git commands.
Do not run git.
"""
    if fetched.kind == "repo":
        text += """
6. Codebase track (this run, kind repo): the chunk list is one entry per macro
   component plus an overview. Name each wiki page after its component
   (NN-<kebab-component>.md, e.g. 02-graph-storage.md), overview first,
   ordered by structural importance. The type for this run is "Codebase".
"""
    return text
