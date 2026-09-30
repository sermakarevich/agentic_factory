"""The summary job: the technical analysis of a clone, or the paper-style
summary of a text."""

from summarise.contract import EntryPlan, FetchedSource, SummariseRequest


def summary_prompt(
    request: SummariseRequest, fetched: FetchedSource, plan: EntryPlan, run_date: str
) -> str:
    """The prompt, with the run date as YYYY-MM-DD for the analysis's metadata line."""
    if fetched.kind == "repo":
        return _technical_analysis(request, fetched, plan, run_date)
    return _text_summary(request, fetched, plan)


def _technical_analysis(
    request: SummariseRequest, fetched: FetchedSource, plan: EntryPlan, run_date: str
) -> str:
    return f"""\
You are writing the technical analysis summary for codebase "{fetched.title}"
({request.url}, type Codebase).

Run work dir (absolute): {fetched.work_dir}

1. Read ONLY {plan.research_dir}/wiki/*.md (never the clone, the chunk files, or the web).

2. Write {plan.research_dir}/summary.md with exactly this layout, grounded in the
   component pages and their file:line citations:
   - Heading: # Technical Analysis: {fetched.title}
   - Metadata lines: **Repository:** {request.url} / **Version analyzed:** <from the
     manifest or unknown> / **Date:** {run_date} / **Wiki:** [[index]]
   - Then these 11 sections in order (omit one only if it genuinely does not
     apply; never leave a stub):
     ## 1. Overview / What Problem It Solves (problem space, then how the repo
     addresses it; name the primary user)
     ## 2. High-Level Architecture (ASCII diagram with │ ▼ ─ ► connectors,
     then a 4–6 step data-flow narrative; state where persistent state lives)
     ## 3. <The Core Abstraction> (renamed after the repo's central concept;
     representation, named kinds/types with file:line, key queries with a
     verbatim snippet)
     ## 4. LLM / External Service Integration (providers, required vs optional
     calls, env vars; or state explicitly that the repo calls no LLM/API)
     ## 5. <The Main Pipeline> (renamed after the primary workflow; step by
     step with file.py:line for every function)
     ## 6. Key Files (table File | Lines | What It Does, 10–20 files by
     structural importance)
     ## 7. Dependencies (table Package | Version constraint | Purpose,
     required first, exact constraint strings)
     ## 8. CLI / Usage Surface (entry points, commands, env-var and config
     tables)
     ## 9. Extensibility Points (which file/class to extend per extension)
     ## 10. Limitations and Gotchas (at least 3 real ones, bold-led bullets)
     ## 11. How It Compares to Alternatives (3–4 real named projects plus a
     positioning sentence)
     ## Appendix: Selected Code Snippets (2–4 verbatim snippets with file and
     line ranges)
   - Direct, dense, analytical prose. No marketing adjectives, no emojis.

Do not run git.
"""


def _text_summary(request: SummariseRequest, fetched: FetchedSource, plan: EntryPlan) -> str:
    return f"""\
You are writing the summary for "{fetched.title}" ({request.url}, type {fetched.type}).

Run work dir (absolute): {fetched.work_dir}

1. Read ONLY {plan.research_dir}/wiki/*.md (never the source, the chunk files, or the web).

2. Write {plan.research_dir}/summary.md:
   - Heading: # {fetched.title}
   - Metadata line for type {fetched.type} (pick the matching variant):
     **Paper:** [..]({request.url}) / **Article:** [..]({request.url}) — <source>, <date> /
     **Video:** [..]({request.url}) — <channel>
   - Sections in order: ## Human Readable TL;DR (3–5 plain sentences with analogies),
     ## TL;DR, then ---, then ## Problem & Motivation, ## Main Original Ideas (numbered,
     with bold names), ## Key Findings, ## Suggestions & Future Directions,
     ## Authors & Institutions.
   - Flowing paragraphs throughout, never one-sentence-per-line.

Do not run git.
"""
