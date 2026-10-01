Write the topic-level overview for the research topic `$topic`.

Focus (what this research must answer): `$focus`.

Read ONLY `$target_dir/topics/*/digest.md`. Read
nothing else: no source folders beyond what those files say, no wiki pages,
no raw sources, never the web.

Write `$target_dir/overview.md` with: `# $topic` - `**Research:** $source_count
sources, $date_range, focus: $focus` - `## Human Readable TL;DR` (3-5
plain sentences with analogies) - `## TL;DR` - `## What is established` (link to `agreements.md`) -
`## What is contested` (one line each, link to `disagreements.md`) -
`## What is open` (link to `open_questions.md`) - `## How to read this
folder`. Flowing paragraphs, never one sentence per line.

Read only the files named above. Never fetch the web or read raw sources. Do not run git — the knowledge base syncs itself.
