"""The implement stage's waves: one unit at a time, or every ready unit at once."""

from autocode.contract import Unit
from autocode.order import waves


def unit(id: str, *after: str) -> Unit:
    return Unit(id=id, title=id, after=list(after))


def ids(found: list[list[Unit]]) -> list[list[str]]:
    return [[item.id for item in wave] for wave in found]


UNITS = [unit("M1"), unit("M2", "M1"), unit("R1", "M1"), unit("R2"), unit("R3", "R1", "M2")]


def test_not_parallel_builds_one_unit_at_a_time_in_the_order_given() -> None:
    assert ids(waves(UNITS, parallel=False)) == [["M1"], ["M2"], ["R1"], ["R2"], ["R3"]]


def test_parallel_builds_the_modules_first_then_every_ready_requirement_at_once() -> None:
    assert ids(waves(UNITS, parallel=True)) == [["M1"], ["M2"], ["R1", "R2"], ["R3"]]


def test_parallel_with_no_after_is_one_wave_of_modules_and_one_of_requirements() -> None:
    units = [unit("M1"), unit("M2"), unit("R1"), unit("R2")]

    assert ids(waves(units, parallel=True)) == [["M1", "M2"], ["R1", "R2"]]


def test_a_requirement_waits_for_a_requirement_even_with_no_module() -> None:
    assert ids(waves([unit("R1"), unit("R2", "R1")], parallel=True)) == [["R1"], ["R2"]]
