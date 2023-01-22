"""A timeline is a set of events on a calendar.

This timeline is used to iterate over program runtime events, manging
the logic for interpreting recurring events for the Rain Bird controller.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable, Iterable, Iterator
from typing import Union

from dateutil import rrule

from .const import DayOfWeek
from .timespan import Timespan

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


class ProgramTimeline:
    """A timeline of events in an irrigation program."""

    def __init__(self, iterable: Iterable[Timespan]) -> None:
        self._iterable = iterable

    def __iter__(self) -> Iterator[Timespan]:
        """Return an iterator as a traversal over events in chronological order."""
        for item in iter(self._iterable):
            yield item.item

    def overlapping(
        self,
        start: datetime.datetime,
        end: datetime.datetime,
    ) -> Iterator[Timespan]:
        """Return an iterator containing events active during the timespan.

        The end date is exclusive.
        """
        timespan = Timespan.of(start, end)
        for item in self._iterable:
            if item.intersects(timespan):
                yield item
            elif item > timespan:
                break


ItemAdapter = Callable[[Union[datetime.datetime]], Timespan]
"""An adapter for an object in a sorted container (iterator).

The adapter is invoked with the date/time of the current instance and
the callback returns an object at that time (e.g. event with updated time)
"""


class RecurIterable(Iterable[Timespan]):
    """A series of events from a recurring event.

    The inputs are a callback that creates objects at a specific date/time, and an iterable
    of all the relevant date/times (typically a dateutil.rrule or dateutil.rruleset).
    """

    def __init__(
        self,
        item_cb: ItemAdapter[Timespan],
        recur: Iterable[datetime.datetime],
    ) -> None:
        """Initialize timeline."""
        self._item_cb = item_cb
        self._recur = recur

    def __iter__(self) -> Iterator[Timespan]:
        """Return an iterator as a traversal over events in chronological order."""
        for dtvalue in self._recur:
            yield self._item_cb(dtvalue)


def custom_recurrence(
    days_of_week: set[DayOfWeek],
    times_of_day: list[datetime.time],
    duration: datetime.timedelta,
    synchro: int,
) -> Iterable[datetime.datetime]:
    """Create a timeline for a CUSTOM program."""
    # Each 'times_of_day' will be its own RRULE.
    # Start counting the dates from 'synchro'
    first_day = datetime.datetime.now() + datetime.timedelta(days=synchro)
    dtstarts = [
        first_day.replace(hour=time_of_day.hour, minute=time_of_day.minute, second=0)
        for time_of_day in times_of_day
    ]
    # Create a RRULE that is FREQ=WEEKLY with every `days_of_week` as the
    # instances within the week.
    byweekday = [RRULE_WEEKDAY[day_of_week] for day_of_week in days_of_week]
    ruleset = rrule.rruleset()
    for dtstart in dtstarts:
        ruleset.rrule(
            rrule.rrule(
                freq=rrule.WEEKLY,
                byweekday=byweekday,
                dtstart=dtstart,
                cache=True,
            )
        )
        # Exclude the first instance
        ruleset.exdate(dtstart)

    return RecurIterable(
        lambda dtstart: Timespan.of(dtstart, dtstart + duration),
        ruleset,
    )


def cyclic_recurrence(
    interval: int,
    times_of_day: list[datetime.time],
    duration: datetime.timedelta,
    synchro: int,
) -> Iterable[datetime.datetime]:
    """Create a timeline for a CUSTOM program."""
    # Each 'times_of_day' will be its own RRULE.
    first_day = datetime.datetime.now() + datetime.timedelta(days=synchro)
    dtstarts = [
        first_day.replace(hour=time_of_day.hour, minute=time_of_day.minute, second=0)
        for time_of_day in times_of_day
    ]
    # Create a RRULE that is FREQ=DAILY with an `interval` between dates
    ruleset = rrule.rruleset()
    for dtstart in dtstarts:
        ruleset.rrule(
            rrule.rrule(
                freq=rrule.DAILY,
                interval=interval,
                dtstart=dtstart,
                cache=True,
            )
        )
        ruleset.exdate(dtstart)

    return RecurIterable(
        lambda dtstart: Timespan.of(dtstart, dtstart + duration),
        ruleset,
    )


def odd_even_recurrence(
    odd_days: bool,
    times_of_day: list[datetime.time],
    duration: datetime.timedelta,
    synchro: int,
) -> Iterable[datetime.datetime]:
    """Create a timeline for a CUSTOM program."""
    # Each 'times_of_day' will be its own RRULE.
    first_day = datetime.datetime.now() + datetime.timedelta(days=synchro)
    dtstarts = [
        first_day.replace(hour=time_of_day.hour, minute=time_of_day.minute, second=0)
        for time_of_day in times_of_day
    ]
    # Create a RRULE that is FREQ=MONTHLY with all odd/even days of the month
    bymonthday = [i for i in range(1, 32) if ((i % 2) == 1) == odd_days]
    ruleset = rrule.rruleset()
    for dtstart in dtstarts:
        ruleset.rrule(
            rrule.rrule(
                freq=rrule.MONTHLY,
                bymonthday=bymonthday,
                dtstart=dtstart,
                cache=True,
            )
        )
        ruleset.exdate(dtstart)

    return RecurIterable(
        lambda dtstart: Timespan.of(dtstart, dtstart + duration),
        ruleset,
    )
