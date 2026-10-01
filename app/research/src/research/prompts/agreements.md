Write the agreements file for the research topic `$topic`.

Focus (what this research must answer): `$focus`.

Read ONLY `$target_dir/topics/*/digest.md` and the source summaries they
link (the `[[<knowledge-relative folder>/summary|...]]` targets, e.g.
`$research_topics_dir/$topic/<Name>/summary.md`).
Read nothing else: no wiki pages, no raw sources, never the web.

Write `$target_dir/agreements.md`: one section per claim that two or more
independent sources support, `## <claim>`, then which sources back it
(with source links), how strong the joint evidence is (kind of sources,
setting, sample, whether they measured the same thing), and any condition
under which the agreement holds ("in controlled tasks", "for novices").
Order sections from strongest to weakest support. Include only real
agreement across sources, not one source repeated, and not points that
`disagreements.md` would contest. Zero sections is a legitimate outcome --
when none is found, say "none found" explicitly with the reason, rather
than inventing consensus.

Read only the files named above. Never fetch the web or read raw sources. Do not run git — the knowledge base syncs itself.
