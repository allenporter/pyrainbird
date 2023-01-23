"""Constants for rainbird."""

from enum import IntEnum


class DayOfWeek(IntEnum):
    """Day of the week."""

    SUNDAY = 0
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6


class ProgramFrequency(IntEnum):
    """Program frequency."""

    CUSTOM = 0
    CYCLIC = 1
    ODD = 2
    EVEN = 3
