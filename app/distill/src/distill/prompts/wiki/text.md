You are writing one wiki page for chunk $chunk_index/$chunk_count
("$chunk_title") of "$title" ($url).

Run work dir (absolute): $work_dir

1. Read ONLY these two files:
   - $chunk_path (the chunk body; your only source of facts)
   - $research_dir/source/plan.md (find your chunk slug $chunk_slug and its planned page
     name; default $chunk_slug.md when absent)
   Do not read any other chunk file, the original source, or the web.

2. Write $research_dir/wiki/<page from plan.md> with exactly this contract:
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

The knowledge base syncs itself and parallel workers share the tree; no git commands.
Do not run git.
