"""The index job: the entry's front page, and the fixes the verifier asks for."""

from summarise.contract import EntryPlan, FetchedSource, SummariseRequest
from summarise.settings.load import settings


def index_prompt(
    request: SummariseRequest, fetched: FetchedSource, plan: EntryPlan, problems: list[str]
) -> str:
    """The prompt; with verifier problems from a failed check it also asks
    for the minimal fixes to the files they name."""
    text = f"""\
You are writing the folder index for "{fetched.title}" ({request.url}).

Run work dir (absolute): {fetched.work_dir}

1. Read {plan.research_dir}/summary.md, {plan.research_dir}/digest.md, and the list of
   {plan.research_dir}/wiki/*.md (never the source or the web).

2. Write {plan.research_dir}/index.md:
   - Front-matter with exactly these keys: type, title, description,
     generated: {{ by: claude/<model you are running as>, at: <current ISO time> }},
     sources: [ {{id: original, resource: {request.url}}},
     {{id: local-copy, resource: source/source.md}} ], tags: [2–5 topic tags].
   - Heading: # {fetched.title}, then 2–3 orientation sentences.
   - ## How to work through this (summary ~2 min → digest ~10 min → wiki pages).
   - ## Read This Folder (links to summary, digest, explainer, critical_thinking,
     questions).
   - ## Wiki table | Page | Covers | with one row per wiki/*.md in order.
   - ## Original Source (link to {request.url} and the local copy source/source.md).
   - Link only to files, never to a folder: write [01](wiki/01-<stem>.md), not
     [wiki](wiki/) (the verifier rejects folder links).

3. Sanity checklist before finishing: every wiki page has **In one sentence:** and
   ## Key points; digest lines are verbatim copies; every page has at least one
   question in questions.md. Report any defect by printing it and exiting with an error
   instead of fixing other workers' files silently.

Do not run git.
"""
    if problems:
        text += _feedback(problems)
    return text


def _feedback(problems: list[str]) -> str:
    listed = "\n".join(f"- {problem}" for problem in problems)
    return f"""
## Verifier problems

The verifier checked the entry after the last index attempt and found these problems.
Fix the named files minimally (missing pages in digest.md, broken links, files of
{settings.verify.min_bytes} bytes or under) and rewrite index.md; do not touch anything
the verifier did not name.

{listed}
"""
