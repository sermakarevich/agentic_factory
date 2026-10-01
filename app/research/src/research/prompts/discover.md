You are running the discover step of a research run into $topics.

Inputs (exact values; missing inputs cannot happen - never invent a focus):

| key | value |
|---|---|
| `topics` | $topics |
| `focus` | $focus |
| `target` | $target |
| `topic` | $topic |
| `n_sources` | $n_sources |
| `lenses` | $lenses |
| `date_from` | $date_from |
| `kinds` | $kinds |

Let `TARGET` = `$target_dir`.
Every aggregate (`index.md`, `overview.md`, `digest.md`, `agreements.md`,
`disagreements.md`, `open_questions.md`, `lenses/`, `topics/`,
`sources.md`) lives under `TARGET`; source summaries stay under
`research_topics/$topic/<Name>/`, filed by their summarise runs.

## 1. Collect candidates (metadata only, never full content)

Collect between $candidates_min and $candidates_max candidates as metadata only:
title, abstract or first paragraph (at most $abstract_chars characters), authors,
date, venue/channel, url, kind. Free routes first:

| kind | route |
|---|---|
| paper | arXiv API (`export.arxiv.org/api/query`), Semantic Scholar API (`api.semanticscholar.org/graph/v1/paper/search`) |
| article | web search; engineering blogs; HN Algolia API (`hn.algolia.com/api/v1/search`) |
| video | web search restricted to youtube.com |
| repo / notebook | GitHub search API (`api.github.com/search/repositories`, `search/code`) |
| thread | **never search X/Twitter blind** (it costs paid credits per tweet); a thread only enters when another route points at it |

Restrict to `$kinds` when given (empty means all kinds).

## 2. Hard filters (no model call)

Drop a candidate if any of these hold:

- duplicate url/title (case-insensitive, near-identical titles) already seen this run;
- older than `$date_from`, when given (empty means no cutoff);
- dead link: a HEAD request fails twice;
- **already in the KB**: normalize the candidate's url (drop scheme and
  `www.`; for arXiv compare the arXiv id; for YouTube compare the video
  id) and compare against every `sources[].resource` entry in the
  front-matter of `$research_dir/*/index.md`,
  `$investment_dir/*/index.md`,
  `$research_dir/*/sources/*/index.md`,
  `$research_topics_dir/*/research/*/index.md`, and
  `$research_topics_dir/*/*/index.md`, plus the URL strings
  in `$research_topics_dir/*/*/summary.md` (topic entries
  whose summary carries no front-matter). A match is kept with
  `status: "in_kb"` and `origin: "<folder that matched, relative to the
  knowledge folder>"` - it is not scored again, only shortlisted for
  linking later (no re-summarise, no move).
- **Skip epic hubs**: a `research/*/` folder that contains a `sources/`
  subdirectory (plural) or whose `index.md` front-matter has
  `type: Research` is a research epic hub, not an entry - skip it for the
  `$research_dir/*/index.md` glob. Its `sources` front-matter holds counts, not
  resources, so it can never be an `in_kb` origin. Only folders with
  `source/source.md` (singular) are entries.

Everything that survives (including `in_kb` matches) becomes a candidate
row; anything dropped is not recorded further.

## 3. Write candidates

Write `$target_dir/candidates.json` as `{"candidates": [...]}` with one object
per surviving candidate: `url`, `title`, `kind`, `authors`, `date`, `venue`,
`abstract`, `status` (`candidate` or `in_kb`), `origin` (the matched folder
relative to the knowledge folder, or empty).

End your final message by stating `candidates_path`: the absolute path of the
file you wrote.

Fetch the web for candidate metadata only; never read full sources. Do not run git — the knowledge base syncs itself.
