You are planning where a fetched source will live in the knowledge base.

Source under study: "$title" ($url, kind $kind).
Run work dir (absolute): $work_dir

1. Read ONLY these two files (never the chunk bodies):
   - $source_md (provenance header only: title, source, kind, fetched, tool)
   - $work_dir/chunks.json (chunk index/slug/title list)
   Do not read $work_dir/chunks/*.md: chunk bodies belong to later workers.

$folder_section

3. Create the layout and copy the source:
   - mkdir -p <research_dir>/source <research_dir>/wiki/images
   - Copy $source_md to <research_dir>/source/source.md.
   - If $work_dir/source.pdf exists and is smaller than $pdf_mb MB, copy it to
     <research_dir>/source/source.pdf too; otherwise pin the PDF location ($url) at the
     top of <research_dir>/source/source.md.

4. Write <research_dir>/source/plan.md: a table mapping each chunk slug to its planned wiki
   page NN-<kebab-topic>.md plus a one-line "covers" note per row.

5. State the plan: research_dir (the absolute research dir), slug (the PascalName),
   title ("$title") and type ("$type").
   Type rule from the source kind ($kind): youtube → Video, pdf → Paper,
   x/article → Article, repo → Codebase. This run: $type.

Do not run git commands.
Do not run git.
