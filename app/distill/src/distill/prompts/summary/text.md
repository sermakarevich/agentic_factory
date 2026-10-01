You are writing the summary for "$title" ($url, type $type).

Run work dir (absolute): $work_dir

1. Read ONLY $research_dir/wiki/*.md (never the source, the chunk files, or the web).

2. Write $research_dir/summary.md:
   - Heading: # $title
   - Metadata line for type $type (pick the matching variant):
     **Paper:** [..]($url) / **Article:** [..]($url) — <source>, <date> /
     **Video:** [..]($url) — <channel>
   - Sections in order: ## Human Readable TL;DR (3–5 plain sentences with analogies),
     ## TL;DR, then ---, then ## Problem & Motivation, ## Main Original Ideas (numbered,
     with bold names), ## Key Findings, ## Suggestions & Future Directions,
     ## Authors & Institutions.
   - Flowing paragraphs throughout, never one-sentence-per-line.

Do not run git.
