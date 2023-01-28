"""Constants for rainbird."""

from enum import IntEnum


class DayOfWeek(IntEnum):
    """Day of the week."""

    SUNDAY = 0
    """Sunday."""

    MONDAY = 1
    """Monday."""

    TUESDAY = 2
    """Tuesday."""

    WEDNESDAY = 3
    """Wednesday."""

    THURSDAY = 4
    """Thursday."""

    FRIDAY = 5
    """Friday."""

    SATURDAY = 6
    """Saturday."""


class ProgramFrequency(IntEnum):
    """Program frequency."""

    CUSTOM = 0
    """A custom schedule with specific days of the week."""

    CYCLIC = 1
    """A schedule that cycles every N days."""

    ODD = 2
    """A schedule that runs on odd days."""

    EVEN = 3
    """A schedule that runs on event days."""
