House style of the knowledge-base tutorials (follow it exactly):

- One folder per tutorial: numbered chapters `00_<slug>.md` / `00_<slug>.ipynb`,
  `01_<slug>...` in reading order, an `index.md`, and a runnable `project/`
  when the topic needs code (Docker Compose where services are needed, `uv`
  with a `pyproject.toml`, Python under `project/src/<package>/` with one
  module per concern, `tests/`, and a `justfile` whose recipes run every
  step: `just` lists them).
- Simple language: the reader is not a domain expert. Explain every term
  and abbreviation the first time it appears, in plain words, before using it.
- A chapter opens with `# NN — <Title>`, then a **What you will learn**
  list of 3 to 6 bullets, then sections that go from why to how.
- Hands-on: every claim is shown with code the reader runs and the real
  output it printed (paste what actually came out, never invented output).
  Commands are run from the tutorial's `project/` folder.
- Small diagrams as ```mermaid blocks where a flow or a structure is easier
  seen than read; tables for settings, options and comparisons.
- Notebooks: a markdown cell before each code cell saying what it does and
  why; the notebook runs top to bottom with no manual step and is saved
  with its outputs.
- Secrets are never written into files: a value the reader must supply is
  `REPLACE_ME` in a `.env.template`, read from `.env` (gitignored).
- Fixed local settings (ports, container names, passwords used only
  locally) are chosen once, listed in `index.md` and never changed by a
  chapter. Prefer unusual host ports so nothing clashes with other local
  services.
- End a chapter with a short recap and what the next chapter builds on it.
