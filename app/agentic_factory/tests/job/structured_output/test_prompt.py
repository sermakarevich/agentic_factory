from pydantic import BaseModel, ConfigDict, Field

from agentic_factory.job.structured_output.prompt import INSTRUCTION, field_lines, wrap_prompt
from agentic_factory.job.summary.prompt import wrap_prompt as wrap_summary


class StructuredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    urls: list[str] = Field(description="the pages to process")
    count: int


def test_the_prompt_names_each_field_with_its_type_and_description() -> None:
    wrapped = wrap_prompt("fetch the index", StructuredOutput.model_json_schema())
    assert wrapped.startswith("fetch the index\n\n" + INSTRUCTION + "\n")
    assert field_lines(StructuredOutput.model_json_schema()) == (
        "- urls (array of string): the pages to process\n- count (integer)"
    )


def test_the_structured_output_request_comes_before_the_summary_request() -> None:
    prompt = wrap_summary(wrap_prompt("do it", StructuredOutput.model_json_schema()))
    assert prompt.index(INSTRUCTION) < prompt.index("end your final message with this json block")
