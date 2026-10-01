from factory_settings.table import Table


class AutocodeSettings(Table):
    provider: str
    model: str
    review_model: str
    job_timeout_sec: int
    job_stall_sec: int
    implement_attempts: int
    gate_attempts: int
    resubmit_attempts: int
    test_timeout_sec: int
    git_timeout_sec: int
    output_tail_chars: int


class Settings(Table):
    autocode: AutocodeSettings
