"""Data models for Rain Bird cloud integration."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
import enum

from mashumaro import DataClassDictMixin, field_options


class CloudStreamSortKey(enum.StrEnum):
    """Sort Key identifiers in the AWS AppSync DeviceStateTable."""

    RSSI = "RSSI"
    RAIN_SENSOR = "Event#RainSensorState"
    CONNECTED = "Connected"
    STATION_PREFIX = "Station"


@dataclass
class DeviceStateRecord(DataClassDictMixin):
    """Represents a database record pushed by AppSync subscriptions."""

    pk: str = field(metadata=field_options(alias="PK"))
    sk: str = field(metadata=field_options(alias="SK"))
    data: str | None = field(default=None, metadata=field_options(alias="Data"))
    timestamp: int | None = field(
        default=None, metadata=field_options(alias="TimeStamp")
    )

    @property
    def updated_at(self) -> datetime.datetime:
        """Get the record updated_at datetime, falling back to current UTC time."""
        if self.timestamp:
            try:
                return datetime.datetime.fromtimestamp(
                    self.timestamp, datetime.timezone.utc
                )
            except (ValueError, OSError, OverflowError):
                pass
        return datetime.datetime.now(datetime.timezone.utc)


@dataclass
class RainSensorStateData(DataClassDictMixin):
    """Represents the inner Data payload for Event#RainSensorState."""

    state: int


@dataclass
class StationStateData(DataClassDictMixin):
    """Represents the inner Data payload for Station<N>."""

    state: int
    remain_sec: int = field(metadata=field_options(alias="remainSec"))
    program_number: int | None = field(
        default=None, metadata=field_options(alias="programNumber")
    )


@dataclass
class ConnectedData(DataClassDictMixin):
    """Represents the inner Data payload for Connected."""

    state: str | int | None = None
    active_station: int | None = field(
        default=None, metadata=field_options(alias="activeStation")
    )
    remain_sec: int | None = field(
        default=None, metadata=field_options(alias="remainSec")
    )
    rain_delay: int | None = field(
        default=None, metadata=field_options(alias="rainDelay")
    )


@dataclass
class CloudStreamEvent:
    """Base class for real-time cloud satellite events."""

    satellite_id: int
    device_uuid: str
    updated_at: datetime.datetime


@dataclass
class StationStateEvent(CloudStreamEvent):
    """Fired when a specific zone/station starts or stops watering."""

    zone: int
    is_watering: bool
    remaining_seconds: int | None
    program_number: int | None


@dataclass
class RainSensorStateEvent(CloudStreamEvent):
    """Fired when the rain sensor detects wet/dry status changes."""

    is_wet: bool


@dataclass
class ConnectionStatusEvent(CloudStreamEvent):
    """Fired with overall connection and active status details."""

    is_connected: bool
    active_station: int | None
    remaining_seconds: int | None
    rain_delay: int | None


@dataclass
class RssiStateEvent(CloudStreamEvent):
    """Fired when device RSSI (signal strength) changes."""

    rssi: int


@dataclass
class GenericCloudStreamEvent(CloudStreamEvent):
    """Catch-all event for any unknown/new sort keys (future-proofing)."""

    event_key: str
    raw_data: str | None
