You are writing chapter $number of a hands-on tutorial in the knowledge base.

Tutorial: $title ($topic), for a $level reader.
Tutorial folder: `$folder`
Shared project: `$project_dir`
The plan of the whole tutorial: `$plan_path`
Your chapter's spec (read it after the rules, it is your task): `$spec_path`

How to teach: read the rules file `$rules` first and follow it. It decides
how the chapter explains things; the house style below decides only how
the files look.

$house_style

Two models to read (never edit them):
- `$style_example`: a finished tutorial, the model of folder layout and
  house style (read its `index.md` and one chapter);
- `$teaching_example`: a notebook built by the rules, the model of how to
  teach.

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
- Teach by the rules and the spec: open by placing the chapter in the
  levels tree, introduce the spec's ideas in its order, simple to medium to
  complex with one new thing per step, and use nothing that this or an
  earlier chapter (per the plan) has not explained.
- Use the plan's running example, its data and the shared helpers in
  `$project_dir`; never invent another one.
- Helper and plumbing code goes in a module under `$project_dir`; a
  notebook cell calls one or two clearly named functions, short, one idea
  per cell.
- After every example and every number, say what it means for us. Mark
  each critical point the spec names, and only those, with the rules'
  callout in its exact format (**Important:** / **What it means for us:** /
  **Why it matters:**); state the limits of a tool, method or metric where
  it is introduced.
- Close the chapter with the spec's 2 to 4 ideas to carry forward.
- Run every command and every piece of code the chapter shows, from
  `$project_dir`, and paste the real output. Code that does not run is a
  bug in the chapter: fix it.
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
- A notebook must execute end to end: run
  `$notebook_command <notebook>` (from `$project_dir`, the way the
  project runs things) until it passes with no error, and leave the
  executed outputs saved in it. A notebook that does not run is not done.
- Run the checks the spec names and meet its done criteria.
- Do not run git.

When every file is written and every check passes, finish with a short
summary of what you wrote and what you ran.
