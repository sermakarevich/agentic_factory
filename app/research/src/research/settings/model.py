from factory_settings.table import Table


class ResearchSettings(Table):
    n_sources: int
    reserve_share: float
    lenses: list[str]
    candidates_per_source_min: int
    candidates_per_source_max: int
    abstract_chars: int


class Settings(Table):
    research: ResearchSettings
