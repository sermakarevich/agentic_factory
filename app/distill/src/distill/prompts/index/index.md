You are writing the folder index for "$title" ($url).

Run work dir (absolute): $work_dir

1. Read $research_dir/summary.md, $research_dir/digest.md, and the list of
   $research_dir/wiki/*.md (never the source or the web).

2. Write $research_dir/index.md:
   - Front-matter with exactly these keys: type, title, description,
     generated: { by: claude/<model you are running as>, at: <current ISO time> },
     sources: [ {id: original, resource: $url},
     {id: local-copy, resource: source/source.md} ], tags: [2–5 topic tags].
   - Heading: # $title, then 2–3 orientation sentences.
   - ## How to work through this (summary ~2 min → digest ~10 min → wiki pages).
   - ## Read This Folder (links to summary, digest, explainer, critical_thinking,
     questions).
   - ## Wiki table | Page | Covers | with one row per wiki/*.md in order.
   - ## Original Source (link to $url and the local copy source/source.md).
   - Link only to files, never to a folder: write [01](wiki/01-<stem>.md), not
     [wiki](wiki/) (the verifier rejects folder links).

3. Sanity checklist before finishing: every wiki page has **In one sentence:** and
   ## Key points; digest lines are verbatim copies; every page has at least one
   question in questions.md. Report any defect by printing it and exiting with an error
   instead of fixing other workers' files silently.

Do not run git.
