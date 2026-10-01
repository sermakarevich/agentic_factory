2. Decide the route from the title and chunk list:
   - Provenance-first rule (BEFORE deriving any folder name): search
     $research/*/source/source.md and
     $investment/*/source/source.md for a `Source:`
     line that equals this run's input ($url, exact string match). If one
     exists, reuse that folder no matter what slug this run would have derived:
     refresh <research_dir>/source/source.md from $source_md, state
     (step 5) that folder's absolute path and its existing folder basename as the
     slug, and continue. No question. Only when no such entry exists, derive a
     candidate folder below.
   - Investment/finance topic → base $investment with a new
     folder <YYYY-MM-DD>-<PascalName>, using $run_date for the date.
   - Anything else → $research/<PascalName>.
   - If the route is genuinely unclear, ask with
     mcp__ask_human__ask_human_question. Never guess.
   - Folder-exists rule. If the candidate folder already exists, do NOT overwrite
     it and do NOT treat it as free; first check which case applies:
     1. Same source (re-run): read <candidate>/source/source.md and compare its
        `Source:` provenance url with this run's input ($url). If they match,
        reuse the folder: refresh <research_dir>/source/source.md from $source_md,
        state the plan (step 5), and continue. No question.
     2. Genuine conflict: the provenance url differs, or source.md is missing or
        unreadable → ask with mcp__ask_human__ask_human_question, passing
        context=<this run's source url $url>. Never guess,
        never overwrite an existing folder.
   - macOS rule: the filesystem is case-insensitive, so research/Livekit and
     research/LiveKit are the same folder. A candidate slug that differs only in
     case from an existing folder is case 2 above, not a new folder.
   - Epic-hub rule: a research/<Name>/ folder that contains a `sources/`
     subdirectory (plural) or whose index.md front-matter has
     `type: Research` is a research epic hub, not an entry. It is NEVER
     reusable as this run's folder, not even when the provenance search
     above found nothing (epic hubs carry no source/source.md, so that
     search never matches them). A candidate that collides with an epic hub,
     including a case-only collision per the macOS rule, is always case 2
     above: ask, never reuse, never write entry files into the hub.