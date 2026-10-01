You are writing the technical analysis summary for codebase "$title"
($url, type Codebase).

Run work dir (absolute): $work_dir

1. Read ONLY $research_dir/wiki/*.md (never the clone, the chunk files, or the web).

2. Write $research_dir/summary.md with exactly this layout, grounded in the
   component pages and their file:line citations:
   - Heading: # Technical Analysis: $title
   - Metadata lines: **Repository:** $url / **Version analyzed:** <from the
     manifest or unknown> / **Date:** $run_date / **Wiki:** [[index]]
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
