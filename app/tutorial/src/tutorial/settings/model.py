from factory_settings.table import Table


class TutorialSettings(Table):
    root: str
    levels: list[str]
    level: str
    formats: list[str]
    review_rounds: int
    rules: str
    notebook: str
    style_example: str
    teaching_example: str
    notebook_command: str
    notebook_cell_timeout_sec: int
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
