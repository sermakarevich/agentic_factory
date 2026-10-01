You are writing the digest for "$title" ($url).

Run work dir (absolute): $work_dir

1. Read ONLY $research_dir/wiki/*.md (never the source, the chunk files, or the web).

2. Write $research_dir/digest.md:
   - Backlink line: > [[index|Wiki]] | [[summary|Summary]]
   - Heading: # $title — Digest
   - Then one section per wiki page in order: ## N. [[wiki/NN-x|Title]] with that page's
     **In one sentence:** line and its ## Key points bullets copied VERBATIM (no
     rewording, no merging).
   - End with ## $closing (5–7 numbered clauses tracing the whole
     source's arc across the pages).

Do not run git.
