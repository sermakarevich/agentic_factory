Write the digest for sub-topic `$title` (`$subtopic`) from its sources.
Every source lives in exactly one place: fresh sources under
`research_topics/$topic/`, already-in-the-KB sources at their origin.
Link to them there; never move or copy them.

Your sources are the keys listed in `$source_keys`. Resolve
each key to its url in the `fresh` list below, then to its row in the
resolution table:

`$fresh`

## Source resolution (authoritative)
$source_table

Rules: `succeeded` means the summarise child run filed the source - read
`<folder>/summary.md` and `<folder>/digest.md`. Any other status means the
source was skipped: write one `| <key> | skipped | <reason> |` row in
`Sources in this sub-topic` (take `<reason>` from the status cell above),
never read its folder, never list it as pending. A `succeeded` folder
missing on disk gets an `unreachable` row with what was tried - still
never pending. Read nothing else.

Already-in-the-KB sources (linked, never re-summarised): read ONLY
`<folder>/summary.md` and `<folder>/digest.md` under the knowledge folder
for each knowledge-relative folder in `$linked_origins` (space-separated; empty when
none). Read nothing else.

Write `$target_dir/topics/$nn-$subtopic/digest.md`
with exactly this shape:

```markdown
> [[../../index|Research]] | [[../../overview|Overview]] | [[../../digest|Digest]]

# $title

**In one sentence:** <what the sources jointly establish on this sub-topic>

## Key points
- 5-8 bullets, each a complete claim with the source(s) behind it as [[<knowledge-relative folder>/summary|<short name>]] (e.g. [[research_topics/$topic/<Name>/summary|Short]])

---
## What the sources agree on
## Where they differ
## Evidence quality
## Sources in this sub-topic
| source | kind | what it contributes |
```

Every claim in Key points carries its source link(s). The `Sources in this
sub-topic` table has one row per source in `$source_keys`
plus `$linked_origins`.

Read only the files named above. Never fetch the web or read raw sources. Do not run git — the knowledge base syncs itself.
