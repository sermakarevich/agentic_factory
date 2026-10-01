Write the disagreements file for the research topic `$topic`.

Focus (what this research must answer): `$focus`.

Read ONLY `$target_dir/topics/*/digest.md` and the source summaries they
link (the `[[<knowledge-relative folder>/summary|...]]` targets, e.g.
`$research_topics_dir/$topic/<Name>/summary.md`).
Read nothing else: no wiki pages, no raw sources, never the web.

Write `$target_dir/disagreements.md`: one section per real contradiction,
`## <claim A> vs <claim B>`, who says what with source links, the likely
reason (different setting, different metric, different date, different
incentive), and which side the evidence favours or "unresolved". Include
only real contradictions, not differences of emphasis. Zero sections is a
legitimate outcome -- when none is found, say "none found" explicitly with
the reason, rather than inventing tension.

Read only the files named above. Never fetch the web or read raw sources. Do not run git — the knowledge base syncs itself.
