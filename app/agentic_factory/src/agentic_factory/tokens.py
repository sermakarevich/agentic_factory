from pydantic import BaseModel, Field


class Tokens(BaseModel):
    """Token counts; used per turn in events and as the total in the result."""

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0

    def __add__(self, other: "Tokens") -> "Tokens":
        return Tokens(
            input=self.input + other.input,
            output=self.output + other.output,
            cache_read=self.cache_read + other.cache_read,
            cache_write=self.cache_write + other.cache_write,
        )


class Usage(BaseModel):
    """Tokens with what they cost: what a run, or part of one, was billed."""

    tokens: Tokens = Field(default_factory=Tokens)
    cost_usd: float = 0.0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(tokens=self.tokens + other.tokens, cost_usd=self.cost_usd + other.cost_usd)
