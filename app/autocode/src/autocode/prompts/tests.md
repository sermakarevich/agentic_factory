You are writing the tests of one unit of a feature, before its code exists.

$rules

$spec

The requirements: `$requirements_path`. Your unit is $unit_id ($unit_title);
its failure cases: `$failures_path`.

Write the unit's tests under `$unit_tests_dir/`, mirroring the code's layout,
with at least one test file the repo's test command finds. Test the
behaviour $unit_id requires and every failure case in its file. Import the
real scaffold objects; fake only external services. Every test must fail
now, since the code is still a scaffold. Write nothing outside that folder.
