Write the topic-level digest for the research topic `$topic`.

Focus (what this research must answer): `$focus`.

Read ONLY `$target_dir/topics/*/digest.md`. Read nothing else: no source
folders, no wiki pages, no raw sources, never the web.

Write `$target_dir/digest.md`: one `## N. [[topics/NN-x/digest|Title]]`
section per sub-topic digest, copying that digest's `**In one sentence:**`
line and its `## Key points` bullets VERBATIM -- no rewording, no merging,
no new claims. This file adds links and order, never new claims. End with
`## The picture in five moves` (5-7 numbered clauses tracing the argument
across the sub-topics).

Read only the files named above. Never fetch the web or read raw sources. Do not run git — the knowledge base syncs itself.
