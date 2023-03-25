"""A timeline is a set of events on a calendar.

This timeline is used to iterate over program runtime events, manging
the logic for interpreting recurring events for the Rain Bird controller.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Iterable
from dataclasses import dataclass

from dateutil import rrule
from ical.iter import (
    LazySortableItem,
    RecurIterable,
    SortableItem,
    SortableItemTimeline,
)
from ical.timespan import Timespan

from .const import DayOfWeek, ProgramFrequency

__all__ = ["ProgramTimeline", "ProgramEvent", "ProgramId"]

_LOGGER = logging.getLogger(__name__)

RRULE_WEEKDAY = {
    DayOfWeek.MONDAY: rrule.MO,
    DayOfWeek.TUESDAY: rrule.TU,
    DayOfWeek.WEDNESDAY: rrule.WE,
    DayOfWeek.THURSDAY: rrule.TH,
    DayOfWeek.FRIDAY: rrule.FR,
    DayOfWeek.SATURDAY: rrule.SA,
    DayOfWeek.SUNDAY: rrule.SU,
}


@dataclass
class ProgramId:
    """An instance of a program event or zone."""

    program: int
    zone: int | None = None

    @property
    def name(self) -> str:
        """Name of the program."""
        letter = chr(ord("A") + self.program)
        name = f"PGM {letter}"
        zone_name = ""
        if self.zone:
            zone_name = f": Zone {self.zone}"
        return f"{name}{zone_name}"


@dataclass
class ProgramEvent:
    """An instance of a program event."""

    program_id: ProgramId
    start: datetime.datetime
    end: datetime.dateetime
    rule: rrule.rrule | None = None

    @property
    def rrule_str(self) -> str | None:
        """Return the recurrence rule string."""
        rule_str = str(self.rule)
        if not self.rule or "DTSTART:" not in rule_str or "RRULE:" not in rule_str:
            return None
        parts = str(self.rule).split("\n")
        if len(parts) != 2:
            return None
        return parts[1].lstrip("RRULE:")


class ProgramTimeline(SortableItemTimeline[Timespan, ProgramEvent]):
    """A timeline of events in an irrigation program."""


def create_recurrence(
    program_id: ProgramId,
    frequency: ProgramFrequency,
    dtstart: datetime.datetime,
    duration: datetime.timedelta,
    synchro: int,
    days_of_week: set[DayOfWeek],
    interval: int,
    delay_days: int = 0,
) -> Iterable[SortableItem[Timespan, ProgramEvent]]:
    """Create a timeline using a recurrence rule."""
    # These weekday or day of month refinemens ared used in specific scenarios
    byweekday = [RRULE_WEEKDAY[day_of_week] for day_of_week in days_of_week]
    odd_days = frequency == ProgramFrequency.ODD
    bymonthday = [i for i in range(1, 32) if ((i % 2) == 1) == odd_days]

    ruleset = rrule.rruleset()
    # Rain delay excludes upcoming days from the schedule
    for i in range(0, delay_days):
        ruleset.exdate(dtstart + datetime.timedelta(days=i))

    # Start the schedule from the previous week/cycle
    if frequency == ProgramFrequency.CYCLIC:
        dtstart += datetime.timedelta(days=synchro - interval)
    else:
        dtstart += datetime.timedelta(days=-7)

    rule: rrule.rrule
    if frequency == ProgramFrequency.CYCLIC:
        # Create a RRULE that is FREQ=DAILY with an `interval` between dates
        rule = rrule.rrule(
            freq=rrule.DAILY,
            interval=interval,
            dtstart=dtstart,
            cache=True,
        )
    elif frequency == ProgramFrequency.CUSTOM:
        # Create a RRULE that is FREQ=WEEKLY with every `days_of_week` as the
        # instances within the week.
        rule = rrule.rrule(
            freq=rrule.WEEKLY,
            byweekday=byweekday,
            dtstart=dtstart,
            cache=True,
        )
    else:
        # Create a RRULE that is FREQ=MONTHLY with all odd/even days of the month
        rule = rrule.rrule(
            freq=rrule.MONTHLY,
            bymonthday=bymonthday,
            dtstart=dtstart,
            cache=True,
        )
    ruleset.rrule(rule)

    def adapter(dtstart: datetime.datetime) -> SortableItem[Timespan, ProgramEvent]:
        dtend = dtstart + duration

        def build() -> ProgramEvent:
            return ProgramEvent(program_id, dtstart, dtend, rule)

        return LazySortableItem(Timespan.of(dtstart, dtend), build)

    return RecurIterable(adapter, ruleset)
