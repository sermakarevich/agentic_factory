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
- Every number the prose states matches an output the chapter shows (to
  the decimals shown), checked after the final run, md chapters included;
  where two results disagree, say why. Claim only the provenance the data
  has: labels a model made are not "human labels" (call them reference
  grades and say in one sentence how they were made).
- A notebook chapter (an `.ipynb` above) follows the KB notebook recipe
  `$notebook`: its parts "Hide plumbing in the helper module", "Build the
  notebook with a script, not by hand", "Execute in place and prove it"
  and the checks of "Validate: run it and check it". Its inventory, report
  and backup parts are for rebuilding an old notebook and do not apply.
  The must-haves:
  - the first code cell is the setup cell: it finds the project root from
    any working directory (the folder holding `pyproject.toml`: the current
    one, its `project/`, then its parents), puts the root's `src/` on
    `sys.path`, imports the helper module and `importlib.reload`s it (a
    kernel started earlier holds the old copy otherwise);
  - build the notebook with an `nbformat` script kept in a temp dir outside
    the tutorial folder, never by hand-editing the JSON: change the script,
    rebuild, execute;
  - a cell that may fall back (offline, a saved copy, a cache) prints which
    path ran (the helper returns it, e.g. "live" or "saved copy"); a live
    result that disagrees with a saved one is shown and explained;
  - smoke-test every helper (`uv run python -c ...`), add a test under
    `project/tests/` (named for this chapter) for each helper whose number
    the prose relies on, and run `uv run pytest` until it passes.
- A notebook must execute end to end: run `$notebook_command <notebook>`
  (from `$project_dir`) until it passes, and leave the outputs saved in it.
- Do not run git.

When every problem is fixed and the checks pass, finish with a short
summary of what you changed.
