"""The build order of the units: the waves the implement stage runs."""

from autocode.contract import MODULE, Unit


def waves(units: list[Unit], parallel: bool) -> list[list[Unit]]:
    """The units in waves, each wave built only once every earlier one is in.
    Not parallel: one unit per wave, in the order given. Parallel: shared
    modules first, then requirements, and each wave holds every unit whose
    `after` units are all in earlier waves."""
    if not parallel:
        return [[unit] for unit in units]
    modules = [unit for unit in units if unit.id.startswith(MODULE)]
    requirements = [unit for unit in units if not unit.id.startswith(MODULE)]
    built: set[str] = set()
    return [*_ready_waves(modules, built), *_ready_waves(requirements, built)]


def _ready_waves(units: list[Unit], built: set[str]) -> list[list[Unit]]:
    """`units` in waves of those whose `after` ids are all in `built`, which
    grows with each wave. A unit whose `after` never gets built (the
    contract forbids it) closes the list as a wave of its own."""
    waiting = list(units)
    found: list[list[Unit]] = []
    while waiting:
        wave = [unit for unit in waiting if set(unit.after) <= built] or waiting[:1]
        found.append(wave)
        built.update(unit.id for unit in wave)
        waiting = [unit for unit in waiting if unit not in wave]
    return found
