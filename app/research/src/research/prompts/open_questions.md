Write the open-questions file for the research topic `$topic`.

Focus (what this research must answer): `$focus`.

Read ONLY `$target_dir/topics/*/digest.md`. Read nothing else: no source
folders, no wiki pages, no raw sources, never the web.

Write `$target_dir/open_questions.md`: numbered questions no source answers,
each with why it matters for `$focus` and which sub-topic it belongs to.
This file is the seed for the next run: a re-run may add a sub-topic per
question.

Read only the files named above. Never fetch the web or read raw sources. Do not run git — the knowledge base syncs itself.
