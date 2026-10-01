You are assigning the ranked sources of a research run into $topics to sub-topics.

Ranked rows (shortlist and reserve with their scores and status), as JSON:

$ranked

Make one model pass over the shortlist + reserve only: assign each
shortlisted source's `subtopic` from `$topics`; if a sub-topic has no
source, swap in the best reserve entry that covers it (its `status`
becomes `"shortlist"`, freeing a slot from the previous last-ranked
shortlist entry, whose `status` becomes `"reserve"`).

Then state the plan:

- `sources`: every shortlisted source, in build order, unique keys. One with
  no origin is fresh: keys `src-01`, `src-02`, ..., at most $n_sources
  entries:
  `{"key": "src-01", "url": "...", "title": "...", "kind": "paper", "subtopic": "<slug>"}`.
  One already in the KB has an `origin` and keys `kb-01`, ...:
  `{"key": "kb-01", "url": "...", "title": "...", "kind": "article", "origin":
  "<folder relative to the knowledge folder>", "subtopic": "<slug>"}`. An origin
  is read and linked in place, never re-summarised and never moved.
- `subtopics`: one entry per sub-topic in `$topics`:
  `{"nn": "01", "subtopic": "<slug>", "title": "<human title>",
  "sources": ["src-01"], "linked": ["<origin>"]}`. `sources` holds this
  sub-topic's fresh keys, `linked` its in-KB origins (a sub-topic may have
  only linked sources).
- `lenses`: one entry per comma-separated name in `$lenses`:
  `{"lens": "tech", "audience": "<who this lens is for>"}`.

State the ResearchPlan JSON (`sources`, `subtopics`, `lenses`) in your
final message.

Read only the files named above. Never fetch the web or read raw sources. Do not run git — the knowledge base syncs itself.
