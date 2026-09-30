"""The wiki jobs: one page per chunk, written in parallel."""

from summarise.contract import EntryPlan, FetchedChunk, FetchedSource, SummariseRequest

NO_GIT = """\
The knowledge base syncs itself and parallel workers share the tree; no git commands.
Do not run git.
"""


def wiki_prompt(
    request: SummariseRequest, fetched: FetchedSource, plan: EntryPlan, chunk: FetchedChunk
) -> str:
    """The prompt for one chunk's page: the component variant for a clone,
    the text variant for everything else."""
    if fetched.kind == "repo":
        return _repo_page(request, fetched, plan, chunk)
    return _text_page(request, fetched, plan, chunk)


def _repo_page(
    request: SummariseRequest, fetched: FetchedSource, plan: EntryPlan, chunk: FetchedChunk
) -> str:
    return f"""\
You are writing one wiki page for macro component "{chunk.title}"
(chunk {chunk.index}/{len(fetched.chunks)}) of codebase "{fetched.title}" ({request.url}).

Run work dir (absolute): {fetched.work_dir}

1. Read ONLY these two files:
   - {chunk.path} (the component's source files; your only source of facts)
   - {plan.research_dir}/source/plan.md (find your chunk slug {chunk.slug} and its planned page
     name; default {chunk.slug}.md when absent)
   Do not read any other chunk file or the web. The clone lives outside the
   knowledge base; never copy it in.

2. Write {plan.research_dir}/wiki/<page from plan.md> with exactly this contract:
   > [[../index|Wiki]] | [[../summary|Summary]] | [[../digest|Digest]]
   # <Component>
   **In one sentence:** <the component's whole job in one sentence>
   ## Key points
   - 5–8 bullets, each a complete claim about what the component does, each
     with file:line citations, not topic labels
   ---
   ## <subsections mirroring the component's modules>  (verbatim code excerpts,
     exact parameter names, tables for config/flags)
   **Covers:** <files/directories this page is grounded in>

3. Every structural claim cites file:line. Never invent content: only claims
   present in the chunk. If the chunk notes truncated files, say which files
   were cut instead of guessing their contents.

{NO_GIT}"""


def _text_page(
    request: SummariseRequest, fetched: FetchedSource, plan: EntryPlan, chunk: FetchedChunk
) -> str:
    return f"""\
You are writing one wiki page for chunk {chunk.index}/{len(fetched.chunks)}
("{chunk.title}") of "{fetched.title}" ({request.url}).

Run work dir (absolute): {fetched.work_dir}

1. Read ONLY these two files:
   - {chunk.path} (the chunk body; your only source of facts)
   - {plan.research_dir}/source/plan.md (find your chunk slug {chunk.slug} and its planned page
     name; default {chunk.slug}.md when absent)
   Do not read any other chunk file, the original source, or the web.

2. Write {plan.research_dir}/wiki/<page from plan.md> with exactly this contract:
   > [[../index|Wiki]] | [[../summary|Summary]] | [[../digest|Digest]]
   # <Topic>
   **In one sentence:** <the chunk's whole argument in one sentence>
   ## Key points
   - 5–8 bullets, each a complete claim with numbers/mechanisms, not a topic label
   ---
   ## <subsections mirroring the source>  (tables, exact numbers, verbatim quotes)
   **Covers:** <section/timestamp range>

3. Never invent content: only claims present in the chunk. If the chunk is empty or
   garbled, still write the page, saying so (title, one-sentence note, Covers line).

{NO_GIT}"""
