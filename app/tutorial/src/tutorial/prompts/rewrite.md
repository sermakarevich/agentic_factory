You are fixing chapter $number of a hands-on tutorial in the knowledge base.
A reviewer checked it against its spec and found problems.

Tutorial: $title ($topic), for a $level reader.
Tutorial folder: `$folder`
Shared project: `$project_dir`
The plan of the whole tutorial: `$plan_path`
Your chapter's spec: `$spec_path`

How to teach: read the rules file `$rules` first and follow it. It decides
how the chapter explains things; the house style below decides only how
the files look.

$house_style

A notebook built by the rules, the model of how to teach (never edit it):
`$teaching_example`.

The chapter's files (fix them in place; create any that is missing):

$outputs

What the reviewer found (fix every one):

$problems

Rules:

- You may ADD more files under `$project_dir` when a fix needs them, named
  for this chapter (`ch$number` or `$number` in the name). Never edit a
  file that was there before this chapter was written or that another
  chapter produces:

$others

- Never edit the plan or the specs under `$specs_dir`, and do not write
  `index.md`.
- Keep teaching by the rules and the spec's teaching points: the plan's
  running example, nothing used before it is explained, one new thing per
  step, helper code in `$project_dir` modules with short cells calling
  clearly named functions, every result interpreted, critical points in the
  rules' callout format (**Important:** / **What it means for us:** /
  **Why it matters:**), and the 2 to 4 ideas to carry forward at the end.
- Run every command and every piece of code the chapter shows, from
  `$project_dir`, and paste the real output.
- A notebook must execute end to end: run `$notebook_command <notebook>`
  (from `$project_dir`) until it passes, and leave the outputs saved in it.
- Do not run git.

When every problem is fixed and the checks pass, finish with a short
summary of what you changed.
