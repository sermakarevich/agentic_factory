from typing import Literal

from factory_settings.table import Table

from agentic_factory.step.reasoning import Reasoning


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


class OpencodeGoSettings(Table):
    default_model: str
    base_url: str
    user_agent: str
    retry_after_default_sec: int


class TypeSafeSettings(Table):
    default_model: str
    price_per_m_input_usd: float
    retry_after_default_sec: int


class JudgeSettings(Table):
    provider: Literal["typesafe"]
    timeout_sec: int
    typesafe: TypeSafeSettings


class StepSettings(Table):
    provider: Literal["opencode"]
    reasoning: Reasoning
    max_tokens: int
    timeout_sec: int
    error_clip_chars: int
    opencode: OpencodeGoSettings
    judge: JudgeSettings


class LogSettings(Table):
    content_width: int


class ConversationSettings(Table):
    tool_output_chars: int
    tool_args_chars: int


class ReportSettings(Table):
    max_chars: int


class StructuredOutputSettings(Table):
    max_chars: int


class Settings(Table):
    """Typed view of settings.toml after dynaconf merged the overrides."""

    job: JobSettings
    harness: HarnessesSettings
    step: StepSettings
    log: LogSettings
    conversation: ConversationSettings
    report: ReportSettings
    structured_output: StructuredOutputSettings
