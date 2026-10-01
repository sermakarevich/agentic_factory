"""The questions job: retrieval-practice questions over every wiki page."""

from distill.contract import DistillRequest, EntryPlan, FetchedSource


def questions_prompt(request: DistillRequest, fetched: FetchedSource, plan: EntryPlan) -> str:
    return f"""\
You are writing retrieval-practice questions for "{fetched.title}" ({request.url}).

Run work dir (absolute): {fetched.work_dir}

1. Read {plan.research_dir}/digest.md plus {plan.research_dir}/wiki/*.md
   (never the source or the web).
   Count the wiki pages: fewer than 5 pages → 6–8 questions; 5–8 pages → 8–12; more
   than 8 pages → 12–20. Cover every wiki page with at least one question and include
   exactly one evaluation question (judgment/recommendation).

2. Write {plan.research_dir}/questions.md:
   - Front-matter: type: Retrieval Prompts, last_reviewed: null, review_count: 0
   - Backlink line: > [[index|Wiki]] | [[summary|Summary]] | [[digest|Digest]]
   - Heading: # Retrieval Practice: {fetched.title}
   - One block per question: ### Qn. <question> followed by > [!tip]- Answer and then
     > <2–4 sentences>. See [[wiki/NN-x|Topic]].

Do not run git.
"""
