You are implementing one unit of a feature against its tests.

$rules

$spec

The requirements: `$requirements_path`. Your unit is $unit_id ($unit_title);
its failure cases: `$failures_path`; its tests: `$unit_tests_dir/`.
It builds on: $after.

Write the code of $unit_id in the scaffold until its tests pass. Run them
with:

    $unit_command

Touch only the code of $unit_id and what it alone needs; never a file under
`$tests_dir/`.
