You are finishing a hands-on tutorial in the knowledge base: its chapters
are written and reviewed.

Tutorial: $title ($topic), for a $level reader.
Tutorial folder: `$folder`
Shared project: `$project_dir`
The plan: `$plan_path`

$house_style

A finished tutorial to read as a model of that style: `$style_example`.

How each chapter ended:

$status_table

1. Read the plan and every chapter. Make one pass for consistency and
   gaps across chapters: the same names, ports and versions everywhere,
   links between chapters that resolve, nothing a later chapter uses that
   no earlier one introduced. Fix only small things (a wrong name, a broken
   link, a missing sentence); never rewrite a chapter, and never touch the
   files of a failed chapter beyond a link.
2. Write `$index_path`: a `# <Title>` heading, what the tutorial is and who
   it is for, in simple language, then `Retrieve chapters with
   `ai show tutorials/$name/<chapter>`.`; a `## Chapters (read in order)`
   list with one line per chapter (a link to its file and what it covers);
   a chapter that failed its review is flagged `**(failed review: <its
   problems in one line>)**` on its line; a `## Runnable project` section
   saying how to run `project/` when there is one (`cd project && just ...`);
   a `## Local settings` table of the fixed settings from the plan.
3. Add one line to `$tutorials_index` in the section that fits the topic
   best (make a new `## ` section only when none fits):
   `- [$name/index.md]($name/index.md) — <what it teaches, in one line>.`
   When a line for `$name` is there already, replace it. Change nothing
   else in that file.

Write only inside `$folder`, plus that one line in `$tutorials_index`.
Do not run git.

State in your final message `index_path` (the absolute index.md you wrote)
and `fixes` (one short entry per small fix you made; empty when none).
