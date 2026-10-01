from factory_settings.table import Table


class TemporalSettings(Table):
    address: str
    namespace: str
    task_queue: str


class RunnerSettings(Table):
    max_concurrent_activities: int


class ProviderSettings(Table):
    max_concurrent: int


class CodersSettings(Table):
    graceful_shutdown_sec: int


class CliSettings(Table):
    slug_chars: int
    id_suffix_chars: int


class JobActivitySettings(Table):
    session_timeout_sec: int
    heartbeat_margin_sec: int
    close_margin_sec: int
    max_attempts: int
    retry_initial_sec: int
    retry_backoff: float
    retry_max_sec: int
    min_retry_delay_sec: int


class ReportActivitySettings(Table):
    close_margin_sec: int
    max_attempts: int


class StructuredOutputActivitySettings(Table):
    close_margin_sec: int
    max_attempts: int


class JudgeActivitySettings(Table):
    close_margin_sec: int
    max_attempts: int


class RecordActivitySettings(Table):
    timeout_sec: int
    max_attempts: int


class DistillWorkflowSettings(Table):
    provider: str
    model: str
    job_timeout_sec: int
    job_stall_sec: int
    index_attempts: int


class ResearchWorkflowSettings(Table):
    provider: str
    model: str
    planning_provider: str
    planning_model: str
    job_timeout_sec: int
    job_stall_sec: int
    planning_timeout_sec: int
    sources_at_once: int


class FetchActivitySettings(Table):
    timeout_sec: int
    max_attempts: int


class VerifyActivitySettings(Table):
    timeout_sec: int
    max_attempts: int


class BeadsSettings(Table):
    home: str
    default_priority: int
    command_timeout_sec: int


class BeadsPollerSettings(Table):
    interval_sec: int
    batch_limit: int
    orphan_timeout_sec: int
    schedule_id: str
    tick_timeout_sec: int


class LocateActivitySettings(Table):
    timeout_sec: int
    max_attempts: int


class CandidatesActivitySettings(Table):
    timeout_sec: int
    max_attempts: int


class Settings(Table):
    temporal: TemporalSettings
    runner: RunnerSettings
    providers: dict[str, ProviderSettings]
    coders: CodersSettings
    cli: CliSettings
    job_activity: JobActivitySettings
    report_activity: ReportActivitySettings
    structured_output_activity: StructuredOutputActivitySettings
    judge_activity: JudgeActivitySettings
    record_activity: RecordActivitySettings
    distill_workflow: DistillWorkflowSettings
    fetch_activity: FetchActivitySettings
    verify_activity: VerifyActivitySettings
    beads: BeadsSettings
    beads_poller: BeadsPollerSettings
    research_workflow: ResearchWorkflowSettings
    locate_activity: LocateActivitySettings
    candidates_activity: CandidatesActivitySettings
