from factory_settings.table import Table


class TemporalSettings(Table):
    address: str
    namespace: str
    task_queue: str


class RunnerSettings(Table):
    max_concurrent_activities: int


class CliSettings(Table):
    job_id_chars: int


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


class RecordActivitySettings(Table):
    timeout_sec: int
    max_attempts: int


class DistillWorkflowSettings(Table):
    provider: str
    model: str
    job_timeout_sec: int
    job_stall_sec: int
    index_attempts: int


class FetchActivitySettings(Table):
    timeout_sec: int
    max_attempts: int


class VerifyActivitySettings(Table):
    timeout_sec: int
    max_attempts: int


class Settings(Table):
    temporal: TemporalSettings
    runner: RunnerSettings
    cli: CliSettings
    job_activity: JobActivitySettings
    report_activity: ReportActivitySettings
    structured_output_activity: StructuredOutputActivitySettings
    record_activity: RecordActivitySettings
    distill_workflow: DistillWorkflowSettings
    fetch_activity: FetchActivitySettings
    verify_activity: VerifyActivitySettings
