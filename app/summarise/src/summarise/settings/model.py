from factory_settings.table import Table


class VaultSettings(Table):
    workdir: str
    research: str
    investment: str
    research_topics: str
    pdf_copy_max_bytes: int


class ThrottleSettings(Table):
    at_once: int
    gap_sec: float


class ThrottlesSettings(Table):
    youtube: ThrottleSettings
    x: ThrottleSettings


class FetchSettings(Table):
    work_root: str
    http_timeout_sec: int
    cli_timeout_sec: int
    max_bytes: int
    user_agent: str
    http_retry_delays_sec: list[float]
    min_text_chars: int
    title_chars: int
    throttle: ThrottlesSettings


class RepoSettings(Table):
    readme_chars: int
    manifest_chars: int
    tree_files_cap: int
    max_file_bytes: int


class ChunkingSettings(Table):
    chars_min: int
    chars_max: int
    chars_default: int
    max_chunks: int
    min_section_chars: int
    badges_only_chars: int
    slug_chars: int


class VerifySettings(Table):
    min_bytes: int


class Settings(Table):
    vault: VaultSettings
    fetch: FetchSettings
    repo: RepoSettings
    chunking: ChunkingSettings
    verify: VerifySettings
