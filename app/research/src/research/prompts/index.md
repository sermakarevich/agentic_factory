Write the hub index for the research topic `$topic` and finalise the ledger.

Topic slugs (space-separated): `$topic_slugs`. Lenses (space-separated): `$lenses`.
Focus (verbatim into the front-matter): `$focus`.

Read ONLY `$target_dir/*.md`,
`$target_dir/topics/*/digest.md`,
`$target_dir/sources.md`,
`$target_dir/lenses/*.md`, and
`$target_dir/candidates.json`. Read nothing else:
no source folders beyond what those files say, no wiki pages, no raw
sources, never the web.

Shortlisted sources (from the ranking, with their scores):

$shortlist_table

Source resolution (authoritative; rendered from the summarise child runs -
folder guesses are replaced by each run's reported `file.path`):

$source_table

Linked sources (already in the KB, never re-summarised):
`$linked`

Write `$target_dir/index.md`: front-matter with `type: Research`, `title`,
`description` (one sentence), `generated` (`by: claude/<model-id>, at:
<ISO-8601 UTC>`), `focus` (verbatim), `topics` (the slugs), `lenses`,
`sources` counts (`processed`, `in_kb`, `unreachable`), `runs` (append a row
`{ at: <ISO date>, added: <n> }`), and `tags` (2-5 lowercase); then the body
sections `## How to work through this`, `## Cross-cutting`,
`## Lenses` (`| lens | for |`), `## Sub-topics`
(`| sub-topic | in one sentence | sources |`), and `## Sources`
(`| source | kind | folder |`).

Own the `$target_dir/sources.md` ledger: when the file does not exist yet,
create it with exactly this header line first:

```
| # | status | kind | score | source | sub-topic |
```

Then ensure it lists every shortlisted source from the table above (one row
per source; never rewrite rows written for other sources, only append
missing ones): fresh sources with `status=processed` and the folder where
they were filed by their summarise file stage (the `folder` column of the
resolution table above); already-in-the-KB sources with `status=in_kb` and
their `origin` folder. A shortlisted source the table above marks with a
non-succeeded status, or that has no folder on disk and no digest row, is
`status=unreachable` with the reason where the folder would go - never
`pending`. A missing or skipped source is a ledger row, never a reason to
fail: write every row the evidence supports and finish.

Register this research in the topic page
`$topic_page` under a
`## Research` section: create the section right above `## Tutorials` if it
is missing (`## Tutorials` itself stays where it is), or at the end of the
file when there is no `## Tutorials`. Add one bullet:
`- [[research/<slug>/index|<slug>]] — <one-line description of $topic>`,
where `<slug>` is the basename of `$target_dir`.
When a bullet for the same target already exists, replace it instead of
duplicating. That topic page is the only file outside
`$target_dir` this step may write.

State `index_path` (the absolute index.md you wrote) in your final message.

Read only the files named above. Never fetch the web or read raw sources. Do not run git — the knowledge base syncs itself.
