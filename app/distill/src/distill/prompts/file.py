"""The file job: move the finished entry under its topic and list it there."""

from distill import vault
from distill.contract import DistillRequest, EntryPlan, FetchedSource


def file_prompt(request: DistillRequest, fetched: FetchedSource, plan: EntryPlan) -> str:
    """The prompt; the topic was validated before the run, so the job never asks."""
    topic_dir = vault.research_topics_dir() / request.topic
    return f"""\
You are filing the finished knowledge-base entry for "{fetched.title}" ({request.url})
into research topic "{request.topic}". The topic was chosen up front: do NOT ask
any confirmation question, just file it.

Entry folder: {plan.research_dir}
Run work dir (absolute): {fetched.work_dir}

1. Resolve the entry folder: {plan.research_dir}. If the folder is missing or
   unreadable, stop and print the problem; exit with an error.

2. Destination rule. Let <Name> be the entry folder's basename; the destination
   is {topic_dir}/<Name>/. If the destination
   already exists, stop and print the collision; exit with an error. Never overwrite,
   never merge, never rename: fail loudly instead.

3. MOVE the entry (never copy):
   ```bash
   mv "{plan.research_dir}" "{topic_dir}/<Name>/"
   test -s "{topic_dir}/<Name>/index.md"
   test ! -e "{plan.research_dir}"
   ```
   Both tests must succeed: a non-empty index.md at the destination and
   nothing left behind.

4. Read the first ~200 lines of
   {topic_dir}/<Name>/summary.md and extract the
   TL;DR: prefer the ## Human Readable TL;DR section, fall back to ## TL;DR.
   Keep it to 1-2 sentences, under 30 words.

5. Read {topic_dir}/{request.topic}.md to match its
   convention, then append one bullet:
   `- [[<Name>/summary]] — <tldr>.`
   (Obsidian ref, em dash separator, trailing period; keep above any
   ## Tutorials section, never inside it).

6. State path: the final folder, the destination from step 2.

Do not run git.
"""
