"""A timeline is a set of events on a calendar.

This timeline is used to iterate over program runtime events, manging
the logic for interpreting recurring events for the Rain Bird controller.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

__all__ = []


MIDNIGHT = datetime.time()


def local_timezone() -> datetime.tzinfo:
    """Get the local timezone to use when converting date to datetime."""
    if local_tz := datetime.datetime.now().astimezone().tzinfo:
        return local_tz
    return datetime.timezone.utc


def normalize_datetime(
    value: datetime.datetime, tzinfo: datetime.tzinfo | None = None
) -> datetime.datetime:
    """Convert date or datetime to a value that can be used for comparison."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=tzinfo if tzinfo else local_timezone())
    return value


@dataclass
class Timespan:
    """An unambiguous definition of a start and end time.

    A timespan is not ambiguous in that it can never be a "floating" time range
    and instead is always aligned to some kind of timezone or utc.
    """

    start: datetime.datetime
    """Return the timespan start as a datetime."""

    end: datetime.datetime
    """Return the timespan end as a datetime."""

    def __post_init__(self) -> None:
        if not self.start.tzinfo:
            raise ValueError(f"Start time did not have a timezone: {self.start}")
        self._tzinfo = self.start.tzinfo

    @classmethod
    def of(  # pylint: disable=invalid-name]
        cls,
        start: datetime.datetime,
        end: datetime.datetime,
    ) -> "Timespan":
        """Create a Timestapn for the specified date range."""
        return Timespan(normalize_datetime(start), normalize_datetime(end))

    @property
    def tzinfo(self) -> datetime.tzinfo:
        """Return the timespan timezone."""
        return self._tzinfo

    @property
    def duration(self) -> datetime.timedelta:
        """Return the timespan duration."""
        return self.end - self.start

    def intersects(self, other: "Timespan") -> bool:
        """Return True if this timespan overlaps with the other event."""
        return (
            other.start <= self.start < other.end
            or other.start < self.end <= other.end
            or self.start <= other.start < self.end
            or self.start < other.end <= self.end
        )

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, Timespan):
            return NotImplemented
        return (self.start, self.end) < (other.start, other.end)

    def __gt__(self, other: Any) -> bool:
        if not isinstance(other, Timespan):
            return NotImplemented
        return (self.start, self.end) > (other.start, other.end)

    def __le__(self, other: Any) -> bool:
        if not isinstance(other, Timespan):
            return NotImplemented
        return (self.start, self.end) <= (other.start, other.end)

    def __ge__(self, other: Any) -> bool:
        if not isinstance(other, Timespan):
            return NotImplemented
        return (self.start, self.end) >= (other.start, other.end)
