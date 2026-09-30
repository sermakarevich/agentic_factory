"""The explainer job: the entry in plain language."""

from summarise.contract import EntryPlan, FetchedSource, SummariseRequest


def explainer_prompt(request: SummariseRequest, fetched: FetchedSource, plan: EntryPlan) -> str:
    return f"""\
You are writing the plain-language explainer for "{fetched.title}" ({request.url}).

Run work dir (absolute): {fetched.work_dir}

1. Read {plan.research_dir}/digest.md plus {plan.research_dir}/wiki/*.md
   (never the source or the web).

2. Write {plan.research_dir}/explainer.md, 80–150 lines:
   - Backlink line: > [[index|Wiki]] | [[summary|Summary]] | [[digest|Digest]]
   - Heading: # {fetched.title} — In Plain Language
   - Sections in order: ## What is this about?, ## Why does it matter?,
     ## How does it work?, ## Where can this be used?, ## Conclusions & takeaways,
     ## Jargon decoder (a table of 5–12 terms with plain definitions).

Do not run git.
"""
