2. The entry folder was chosen up front: <research_dir> is $target_dir
   and the slug is its basename. Do NOT derive a folder name and do NOT ask
   where the entry lives.
   - If the folder does not exist, create it.
   - If it holds source/source.md whose `Source:` line equals this run's
     input ($url, exact string match), this is a re-run: refresh
     source/source.md from $source_md and continue.
   - If it holds source/source.md with a different `Source:` line, or a
     `sources/` subdirectory (a research epic hub), it belongs to another
     entry: ask with mcp__ask_human__ask_human_question, passing
     context=<this run's source url $url>. Never overwrite it.
   - A folder without source/source.md (empty or half built) is used as is.