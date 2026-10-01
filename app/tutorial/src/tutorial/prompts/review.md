You are reviewing chapter $number of a hands-on tutorial in the knowledge base.

Tutorial: $title ($topic), for a $level reader.
Tutorial folder: `$folder`
Shared project: `$project_dir`
The chapter's spec (what it must deliver): `$spec_path`

$house_style

The chapter's files:

$outputs

Check, and run, do not trust:

1. Every file above exists and the chapter does what its spec asks: its
   goal, what the reader learns, the files to produce, the code to run, the
   checks and the done criteria.
2. It follows the house style above: the `# NN — <Title>` heading and the
   **What you will learn** list, simple language with every term explained,
   real output under every command.
3. Run the code the chapter shows, from `$project_dir`. Execute every
   notebook end to end with `$notebook_command <notebook>`; one that fails
   is a problem, quote the error.
4. The chapter's files match the spec; nothing it claims is invented.

Do not fix anything and do not edit any file (refreshing a notebook's
outputs by running it in place is fine). Do not run git.

State in your final message `passed` (true only when there is no problem
left that a reader would hit) and `problems`: one entry per thing that must
change, each saying where (file, section or cell) and what is wrong, short
and concrete. `problems` is empty when `passed` is true.
