You are writing the scaffold of a feature: every object it needs, empty.

$rules

$spec

The requirements: `$requirements_path`. The failure cases: `$failures_dir/`.

Units, in build order:

$units

Write every module, class and function the units need, where the repo's
layout puts them, with real signatures and types and no behaviour: each
body raises `NotImplementedError` (or the language's equal). Give each
object a temporary docstring saying what it must do, its unit, what it
depends on and what depends on it. Write no test.
