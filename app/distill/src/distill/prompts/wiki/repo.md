You are writing one wiki page for macro component "$chunk_title"
(chunk $chunk_index/$chunk_count) of codebase "$title" ($url).

Run work dir (absolute): $work_dir

1. Read ONLY these two files:
   - $chunk_path (the component's source files; your only source of facts)
   - $research_dir/source/plan.md (find your chunk slug $chunk_slug and its planned page
     name; default $chunk_slug.md when absent)
   Do not read any other chunk file or the web. The clone lives outside the
   knowledge base; never copy it in.

2. Write $research_dir/wiki/<page from plan.md> with exactly this contract:
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

The knowledge base syncs itself and parallel workers share the tree; no git commands.
Do not run git.
