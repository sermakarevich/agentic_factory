from typing import Literal

from factory_settings.table import Table


class JobSettings(Table):
    provider: Literal["claude", "opencode"]
    timeout_sec: int
    stall_sec: int
    exit_wait_sec: int
    usage_wait_sec: int
    compact_at_tokens: int
    context_limit_tokens: int
    line_limit_bytes: int
    failure_tail_chars: int
    error_clip_chars: int


class HarnessSettings(Table):
    default_model: str


class ClaudeHarnessSettings(HarnessSettings):
    autocompact_min_tokens: int


class HarnessesSettings(Table):
    opencode: HarnessSettings
    claude: ClaudeHarnessSettings


class TypeSafeSettings(Table):
    default_model: str
    price_per_m_input_usd: float
    retry_after_default_sec: int


class JudgeSettings(Table):
    provider: Literal["typesafe"]
    timeout_sec: int
    typesafe: TypeSafeSettings


class StepSettings(Table):
    judge: JudgeSettings


class LogSettings(Table):
    content_width: int


class Settings(Table):
    """Typed view of settings.toml after dynaconf merged the overrides."""

    job: JobSettings
    harness: HarnessesSettings
    step: StepSettings
    log: LogSettings
