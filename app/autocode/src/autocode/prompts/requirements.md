You are writing the requirements of a feature, the first stage of building it.

$rules

$spec

Read the repo first: its layout, its code, its tests and its docs. Then
write `$requirements_path` with two sections:

1. `# Shared modules`: one `## M1 <name>`, `## M2 <name>` ... per module
   that several requirements need (none when there is none). Each says what
   it holds and which requirements use it.
2. `# Requirements`: one `## R1 <name>`, `## R2 <name>` ... per requirement.
   Each states the observable behaviour, its inputs and outputs, and which
   shared module(s) it needs.

Every unit (an M or an R) is small enough for one worker in one sitting.
Write only that file; no code, no tests.

Submit as the output every unit in build order: the shared modules first,
then the requirements. A unit's `after` lists the units it builds on, each
listed before it. Set `parallel` to true only when the units touch separate
files, so they can be built at the same time.
