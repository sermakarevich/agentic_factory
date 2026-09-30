set positional-arguments

# agentic_factory — monorepo commands. Run `just` to list them.
# Each package has its own justfile; these recipes fan out to them.

packages := "app/agent_factory runners/temporal_agent_factory"

# default: show available recipes
default:
    @just --list

# install / sync every workspace member into one .venv
sync:
    uv sync --all-packages

# lint + format check + types + tests for every package
check:
    for p in {{packages}}; do just --justfile $p/justfile --working-directory $p check || exit 1; done

# tests for every package
test *ARGS:
    for p in {{packages}}; do just --justfile $p/justfile --working-directory $p test {{ARGS}} || exit 1; done

# format every package
fmt:
    for p in {{packages}}; do just --justfile $p/justfile --working-directory $p fmt || exit 1; done

# install the `temporal` CLI
temporal-install:
    just --justfile runners/temporal_agent_factory/justfile --working-directory runners/temporal_agent_factory temporal-install

# start the local Temporal dev server (gRPC 127.0.0.1:7233, UI :8233, history in a SQLite file)
temporal:
    just --justfile runners/temporal_agent_factory/justfile --working-directory runners/temporal_agent_factory temporal

# is the dev server up?
temporal-health:
    just --justfile runners/temporal_agent_factory/justfile --working-directory runners/temporal_agent_factory temporal-health

# start the Temporal runner (polls task queues)
runner *ARGS:
    just --justfile runners/temporal_agent_factory/justfile --working-directory runners/temporal_agent_factory runner "$@"

# Start one job on Temporal and wait for it (needs `just temporal` and `just runner`): just run "prompt" --model ...
run *ARGS:
    just --justfile runners/temporal_agent_factory/justfile --working-directory runners/temporal_agent_factory run "$@"

# Run one llm job directly (no Temporal) and watch its events: just job "prompt" --model ...
job *ARGS:
    just --justfile app/agent_factory/justfile --working-directory app/agent_factory run "$@"

# One step, a structured-output request (OpenCode Go API); no args = demo. See app/agent_factory/justfile.
step *ARGS:
    just --justfile app/agent_factory/justfile --working-directory app/agent_factory step "$@"
