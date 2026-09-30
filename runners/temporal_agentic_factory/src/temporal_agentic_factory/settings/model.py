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


class OutputsActivitySettings(Table):
    close_margin_sec: int
    max_attempts: int


class RecordActivitySettings(Table):
    timeout_sec: int
    max_attempts: int


class Settings(Table):
    temporal: TemporalSettings
    runner: RunnerSettings
    cli: CliSettings
    job_activity: JobActivitySettings
    report_activity: ReportActivitySettings
    outputs_activity: OutputsActivitySettings
    record_activity: RecordActivitySettings
