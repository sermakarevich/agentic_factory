from pydantic import BaseModel


class JobSettings(BaseModel):
    provider: str
    timeout_sec: int
    stall_sec: int
    compact_at_tokens: int
    context_limit_tokens: int
    line_limit_bytes: int
    failure_tail_chars: int
    error_clip_chars: int


class HarnessSettings(BaseModel):
    default_model: str


class ClaudeHarnessSettings(HarnessSettings):
    autocompact_min_tokens: int


class HarnessesSettings(BaseModel):
    opencode: HarnessSettings
    claude: ClaudeHarnessSettings


class OpencodeGoSettings(BaseModel):
    default_model: str
    base_url: str
    user_agent: str
    retry_after_default_sec: int


class StepSettings(BaseModel):
    provider: str
    reasoning: str
    max_tokens: int
    timeout_sec: int
    error_clip_chars: int
    opencode: OpencodeGoSettings


class LogSettings(BaseModel):
    content_width: int


class StoreSettings(BaseModel):
    url: str


class Settings(BaseModel):
    """Typed view of settings.toml after dynaconf merged the overrides."""

    job: JobSettings
    harness: HarnessesSettings
    step: StepSettings
    log: LogSettings
    store: StoreSettings
