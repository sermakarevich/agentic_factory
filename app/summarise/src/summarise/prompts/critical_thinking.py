"""The critical-thinking job: claims against evidence, and a verdict."""

from summarise.contract import EntryPlan, FetchedSource, SummariseRequest


def critical_thinking_prompt(
    request: SummariseRequest, fetched: FetchedSource, plan: EntryPlan
) -> str:
    return f"""\
You are writing the critical analysis for "{fetched.title}" ({request.url}).

Run work dir (absolute): {fetched.work_dir}

1. Read {plan.research_dir}/digest.md plus {plan.research_dir}/wiki/*.md
   (never the source or the web).

2. Write {plan.research_dir}/critical_thinking.md, 60–120 lines:
   - Backlink line: > [[index|Wiki]] | [[summary|Summary]] | [[digest|Digest]]
   - Heading: # Critical Analysis: {fetched.title}
   - Sections in order: ## Claims vs. evidence, ## Genuinely new vs. repackaged,
     ## Weaknesses and blind spots, ## Applicability (including a
     **Relevance to my work** bullet list for AI/ML engineering, agentic systems, and
     the Elisity data platform), ## What this changes,
     ## Verdict ending with a bold call: **adopt** / **trial** / **watch** / **skip**.

Do not run git.
"""
