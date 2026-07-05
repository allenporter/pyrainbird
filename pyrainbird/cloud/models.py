"""Data models for Rain Bird cloud integration."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
import enum
from typing import Any

from mashumaro import DataClassDictMixin, field_options
from mashumaro.config import BaseConfig


SUBSCRIBE_DEVICE_STATE_QUERY = (
    "subscription onUpdateDeviceStateTable($PK : String!) {\n"
    "  onUpdateDeviceStateTable(PK: $PK) {\n"
    "    PK\n"
    "    SK\n"
    "    Data\n"
    "    TimeStamp\n"
    "  }\n"
    "}"
)


@dataclass
class WebSocketMessage(DataClassDictMixin):
    """Represents a protocol message sent over the AppSync GraphQL WebSocket."""

    type: CloudStreamMessageType
    id: str | None = None
    payload: dict[str, Any] | None = None

    class Config(BaseConfig):
        omit_none = True


@dataclass
class SubscriptionQueryData(DataClassDictMixin):
    """Holds GraphQL query and variable variables for DeviceStateTable updates."""

    query: str
    variables: dict[str, Any]


@dataclass
class SubscriptionAuthorization(DataClassDictMixin):
    """Authorization parameters for AppSync connection headers."""

    host: str
    authorization: str = field(metadata=field_options(alias="Authorization"))


@dataclass
class SubscriptionExtensions(DataClassDictMixin):
    """AppSync WebSocket payload authorization extension envelope."""

    authorization: SubscriptionAuthorization


@dataclass
class SubscriptionStartPayload(DataClassDictMixin):
    """AppSync subscription 'start' payload data."""

    data: str
    extensions: SubscriptionExtensions


class CloudStreamSortKey(enum.StrEnum):
    """Sort Key identifiers in the AWS AppSync DeviceStateTable."""

    RSSI = "RSSI"
    RAIN_SENSOR = "Event#RainSensorState"
    CONNECTED = "Connected"
    STATION_PREFIX = "Station"


class CloudStreamMessageType(enum.StrEnum):
    """Message types used in the AppSync GraphQL WebSocket protocol."""

    CONNECTION_INIT = "connection_init"
    CONNECTION_ACK = "connection_ack"
    START = "start"
    DATA = "data"
    KEEP_ALIVE = "ka"
    CONNECTION_ERROR = "connection_error"
    ERROR = "error"
    COMPLETE = "complete"


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
