You are writing retrieval-practice questions for "$title" ($url).

Run work dir (absolute): $work_dir

1. Read $research_dir/digest.md plus $research_dir/wiki/*.md
   (never the source or the web).
   Count the wiki pages: fewer than 5 pages → 6–8 questions; 5–8 pages → 8–12; more
   than 8 pages → 12–20. Cover every wiki page with at least one question and include
   exactly one evaluation question (judgment/recommendation).

2. Write $research_dir/questions.md:
   - Front-matter: type: Retrieval Prompts, last_reviewed: null, review_count: 0
   - Backlink line: > [[index|Wiki]] | [[summary|Summary]] | [[digest|Digest]]
   - Heading: # Retrieval Practice: $title
   - One block per question: ### Qn. <question> followed by > [!tip]- Answer and then
     > <2–4 sentences>. See [[wiki/NN-x|Topic]].

Do not run git.
