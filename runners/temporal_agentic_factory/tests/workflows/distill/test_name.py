from temporal_agentic_factory.workflows.distill.name import source_name


def test_a_url_is_named_by_its_host_and_last_segment() -> None:
    assert source_name("https://arxiv.org/abs/2401.12345") == "arxiv.org/2401.12345"
    assert source_name("https://example.org/") == "example.org"


def test_a_local_path_is_named_by_its_file() -> None:
    assert source_name("/tmp/papers/memory.pdf") == "memory.pdf"
