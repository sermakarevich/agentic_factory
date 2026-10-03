You are reviewing chapter $number of a hands-on tutorial in the knowledge base.

Tutorial: $title ($topic), for a $level reader.
Tutorial folder: `$folder`
Shared project: `$project_dir`
The plan of the whole tutorial: `$plan_path`
The chapter's spec (what it must deliver): `$spec_path`

How to teach: read the rules file `$rules` first and check the chapter
against it; the house style below is only how the files look. A notebook
is built and checked by the KB notebook recipe `$notebook`.

$house_style

The chapter's files:

$outputs

Check, and run, do not trust:

1. Every file above exists and the chapter does what its spec asks: its
   goal, what the reader learns, the files to produce, the code to run, the
   checks and the done criteria.
2. It follows the house style above: the `# NN — <Title>` heading and the
   **What you will learn** list, real output under every command or cell
   shown, the project layout.
3. Run the code the chapter shows, from `$project_dir`. Execute every
   notebook end to end with `$notebook_command <notebook>`; one that fails
   is a problem, quote the error.
4. The chapter's files match the spec; nothing it claims is invented.
5. It teaches by the rules and the spec. Each of these is a problem:
   - something used before it is explained, in this chapter or an earlier
     one per the plan;
   - a step that adds more than one new thing;
   - a critical point not in the rules' callout format (**Important:** /
     **What it means for us:** / **Why it matters:**), or a callout on
     something that is not critical;
   - a result or a number left uninterpreted;
   - a tool, method or metric introduced without its limits;
   - the plan's running example not used (another example in its place);
   - no closing 2 to 4 ideas to carry forward.
6. It tells the truth, in md chapters too. Each of these is a problem:
   - a number in the prose that no output shows, or shows with another
     value (read the outputs after your own run);
   - a provenance claim the data does not support (e.g. "human labels"
     that a model made);
   - a fallback that hides which path ran, or a live and a saved result
     that contradict each other with no word on why;
   - a notebook whose first code cell is not the setup cell (project root
     found from any working directory, the helper module
     `importlib.reload`ed);
   - a helper that computes a number the prose relies on with no test
     under `$project_dir/tests/`.

Do not fix anything and do not edit any file (refreshing a notebook's
outputs by running it in place is fine). Do not run git.

State in your final message `passed` (true only when there is no problem
left that a reader would hit) and `problems`: one entry per thing that must
change, each saying where (file, section or cell) and what is wrong, short
and concrete. `problems` is empty when `passed` is true.
