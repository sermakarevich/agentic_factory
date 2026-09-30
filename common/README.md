# common

Libraries reused by two or more apps, one named package per folder
(`common/<package>/pyproject.toml`, `src/<package>/`, `tests/`).

A module moves here only when a second app needs it, never
speculatively. `common/` is a folder of packages, not a Python module
named `common`.
