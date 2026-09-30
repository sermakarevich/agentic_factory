from pydantic import BaseModel


class TemporalSettings(BaseModel):
    address: str
    namespace: str
    task_queue: str


class RunnerSettings(BaseModel):
    max_concurrent_activities: int


class JobActivitySettings(BaseModel):
    session_timeout_sec: int
    heartbeat_margin_sec: int
    close_margin_sec: int
    max_attempts: int
    retry_initial_sec: int
    retry_backoff: float
    retry_max_sec: int
    min_retry_delay_sec: int


class StepActivitySettings(BaseModel):
    timeout_sec: int
    max_attempts: int


class Settings(BaseModel):
    temporal: TemporalSettings
    runner: RunnerSettings
    job_activity: JobActivitySettings
    step_activity: StepActivitySettings
