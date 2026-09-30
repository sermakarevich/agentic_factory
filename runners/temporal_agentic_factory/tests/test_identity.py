from temporal_agentic_factory.identity import code_version, runner_identity


def test_identity_names_host_pid_and_code_version() -> None:
    host, pid, version = runner_identity().split(":")
    assert host and pid.isdigit() and version == code_version()
