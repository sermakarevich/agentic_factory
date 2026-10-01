You are writing chapter $number of a hands-on tutorial in the knowledge base.

Tutorial: $title ($topic), for a $level reader.
Tutorial folder: `$folder`
Shared project: `$project_dir`
The plan of the whole tutorial: `$plan_path`
Your chapter's spec (read it first, it is your task): `$spec_path`

$house_style

A finished tutorial to read as a model of that style: `$style_example`
(read its `index.md` and one chapter; never edit it).

Write exactly these files of this chapter, all of them:

$outputs

Rules:

- You may ADD more files under `$project_dir` when the spec needs them,
  named for this chapter (`ch$number` or `$number` in the name). Never edit
  a file that was there before you started or that another chapter
  produces; other chapters own these, and they are written at the same
  time as yours:

$others

- The plan and the specs under `$specs_dir` are the designer's; read them,
  never edit them. Do not write `index.md`.
- Run every command and every piece of code the chapter shows, from
  `$project_dir`, and paste the real output. Code that does not run is a
  bug in the chapter: fix it.
- A notebook must execute end to end: run
  `$notebook_command <notebook>` (from `$project_dir`, the way the
  project runs things) until it passes with no error, and leave the
  executed outputs saved in it. A notebook that does not run is not done.
- Run the checks the spec names and meet its done criteria.
- Do not run git.

When every file is written and every check passes, finish with a short
summary of what you wrote and what you ran.
