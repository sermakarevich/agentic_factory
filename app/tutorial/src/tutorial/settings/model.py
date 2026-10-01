from factory_settings.table import Table


class TutorialSettings(Table):
    root: str
    levels: list[str]
    level: str
    formats: list[str]
    review_rounds: int
    style_example: str
    notebook_command: str
    naming_timeout_sec: int
    finish_timeout_sec: int


class CoderSettings(Table):
    provider: str
    model: str
    timeout_sec: int
    stall_sec: int


class Settings(Table):
    tutorial: TutorialSettings
    designer: CoderSettings
    writer: CoderSettings
    reviewer: CoderSettings
