"""A timeline is a set of events on a calendar.

This timeline is used to iterate over program runtime events, manging
the logic for interpreting recurring events for the Rain Bird controller.
"""

from __future__ import annotations

import datetime
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

__all__ = ["ProgramTimeline"]

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
class ProgramEvent:
    """An instance of a program event."""

    start: datetime.datetime
    end: datetime.dateetime


class ProgramTimeline(SortableItemTimeline[Timespan, ProgramEvent]):
    """A timeline of events in an irrigation program."""

    def __init__(
        self, iterable: Iterable[SortableItem[Timespan, ProgramEvent]]
    ) -> None:
        super().__init__(iterable)


def create_timeline(
    frequency: ProgramFrequency,
    times_of_day: list[datetime.time],
    duration: datetime.timedelta,
    synchro: int,
    days_of_week: set[DayOfWeek],
    interval: int,
) -> ProgramTimeline:
    """Create a timeline using a recurrence rule."""

    # Each 'times_of_day' will be its own RRULE.
    # Start counting the dates from 'synchro'
    first_day = datetime.datetime.now() + datetime.timedelta(days=synchro)
    dtstarts = [
        first_day.replace(hour=time_of_day.hour, minute=time_of_day.minute, second=0)
        for time_of_day in times_of_day
    ]

    # These weekday or day of month refinemens only used in specific scenarios
    byweekday = [RRULE_WEEKDAY[day_of_week] for day_of_week in days_of_week]
    odd_days = frequency == ProgramFrequency.ODD
    bymonthday = [i for i in range(1, 32) if ((i % 2) == 1) == odd_days]

    ruleset = rrule.rruleset()
    for dtstart in dtstarts:
        # Exclude the first instance
        ruleset.exdate(dtstart)

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
            return ProgramEvent(dtstart, dtend)

        return LazySortableItem(Timespan.of(dtstart, dtend), build)

    return ProgramTimeline(RecurIterable(adapter, ruleset))
