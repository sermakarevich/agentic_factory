You are writing the end-to-end tests of a feature, before its code exists.

$rules

$spec

The requirements: `$requirements_path`.

Write tests under `$e2e_dir/`, with at least one test file the repo's test
command finds, that drive the feature's real flow from its entry point
through every requirement, as a user of it would. Use the real scaffold
objects; fake only external services. Every test must fail now, since the
code is still a scaffold. Write nothing outside that folder.
