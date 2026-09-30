from pydantic import BaseModel, ConfigDict


class Table(BaseModel):
    """One table of a settings.toml, typed. A key that is not a field is a
    typo, not an override, so it is refused."""

    model_config = ConfigDict(extra="forbid")
