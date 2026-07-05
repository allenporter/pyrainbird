"""Data models for Rain Bird cloud integration."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
import enum
from typing import Any
import json

from mashumaro import DataClassDictMixin, field_options
from mashumaro.config import BaseConfig


SUBSCRIBE_DEVICE_STATE_QUERY = """
subscription onUpdateDeviceStateTable($PK : String!) {
  onUpdateDeviceStateTable(PK: $PK) {
    PK
    SK
    Data
    TimeStamp
  }
}
""".strip()


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

    @property
    def is_wet(self) -> bool:
        """Return True if the rain sensor is wet."""
        return self.state == 1


@dataclass
class StationStateData(DataClassDictMixin):
    """Represents the inner Data payload for Station<N>."""

    state: int
    remain_sec: int = field(metadata=field_options(alias="remainSec"))
    program_number: int | None = field(
        default=None, metadata=field_options(alias="programNumber")
    )

    @classmethod
    def parse_record(cls, record: DeviceStateRecord) -> StationStateData:
        """Parse a StationStateData from a DeviceStateRecord."""
        if not record.data:
            raise ValueError("No data found in record")
        try:
            record_data = json.loads(record.data)
        except json.JSONDecodeError as err:
            raise ValueError(f"Failed to parse record data: {err}")
        if (
            remain_sec := record_data.get("remainSec", 0)
        ) > 1000000000 and record.timestamp:
            if remain_sec >= record.timestamp:
                record_data["remainSec"] = remain_sec - record.timestamp
        return cls.from_dict(record_data)

    @property
    def is_watering(self) -> bool:
        """Return True if the station is watering."""
        return self.state == 1


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

    @classmethod
    def parse_record(cls, record: DeviceStateRecord) -> ConnectedData:
        """Parse a ConnectedData from a DeviceStateRecord."""
        if not record.data:
            raise ValueError("No data found in record")
        try:
            record_data = json.loads(record.data)
        except json.JSONDecodeError as err:
            raise ValueError(f"Failed to parse record data: {err}")

        if isinstance(record_data, dict):
            if (remain_sec := record_data.get("remainSec")) is not None:
                if remain_sec > 1000000000 and record.timestamp:
                    if remain_sec >= record.timestamp:
                        record_data["remainSec"] = remain_sec - record.timestamp
            return cls.from_dict(record_data)

        # Handle scalar (e.g. 0, "offline")
        return cls(state=record_data)

    @property
    def is_connected(self) -> bool:
        """Return True if the state indicates a connected status."""
        return str(self.state) not in ("0", "offline")


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
    data: StationStateData

    @property
    def is_watering(self) -> bool:
        """Return True if the station is watering."""
        return self.data.is_watering

    @property
    def remaining_seconds(self) -> int | None:
        """Return the remaining duration in seconds."""
        return self.data.remain_sec

    @property
    def program_number(self) -> int | None:
        """Return the active program number."""
        return self.data.program_number


@dataclass
class RainSensorStateEvent(CloudStreamEvent):
    """Fired when the rain sensor detects wet/dry status changes."""

    data: RainSensorStateData

    @property
    def is_wet(self) -> bool:
        """Return True if the rain sensor is wet."""
        return self.data.is_wet


@dataclass
class ConnectionStatusEvent(CloudStreamEvent):
    """Fired with overall connection and active status details."""

    data: ConnectedData

    @property
    def is_connected(self) -> bool:
        """Return True if the state indicates a connected status."""
        return self.data.is_connected

    @property
    def active_station(self) -> int | None:
        """Return the currently active watering station, if any."""
        return self.data.active_station

    @property
    def remaining_seconds(self) -> int | None:
        """Return the remaining duration for the active station."""
        return self.data.remain_sec

    @property
    def rain_delay(self) -> int | None:
        """Return the active rain delay duration."""
        return self.data.rain_delay


@dataclass
class RssiStateEvent(CloudStreamEvent):
    """Fired when device RSSI (signal strength) changes."""

    rssi: int


@dataclass
class GenericCloudStreamEvent(CloudStreamEvent):
    """Catch-all event for any unknown/new sort keys (future-proofing)."""

    event_key: str
    raw_data: str | None


def deserialize_hhmmss(val: str | None) -> datetime.timedelta:
    """Parse a duration string formatted as HH:MM:SS into a timedelta."""
    if not val:
        return datetime.timedelta()
    try:
        parts = val.split(":")
        if len(parts) == 3:
            h, m, s = map(int, parts)
            return datetime.timedelta(hours=h, minutes=m, seconds=s)
    except (ValueError, TypeError, OverflowError):
        pass
    return datetime.timedelta()


@dataclass
class CloudProgram(DataClassDictMixin):
    id: int
    name: str
    short_name: str = field(metadata=field_options(alias="shortName"))
    is_enabled: bool = field(metadata=field_options(alias="isEnabled"))
    start_time: str = field(metadata=field_options(alias="startTime"))
    week_days: str = field(metadata=field_options(alias="weekDays"))
    program_adjust: int = field(metadata=field_options(alias="programAdjust"))


@dataclass
class CloudProgramRuntime(DataClassDictMixin):
    program_id: int = field(metadata=field_options(alias="programId"))
    program_short_name: str = field(metadata=field_options(alias="programShortName"))
    base_run_time: datetime.timedelta = field(
        metadata=field_options(alias="baseRunTime", deserialize=deserialize_hhmmss)
    )
    adjusted_run_time: datetime.timedelta = field(
        metadata=field_options(alias="adjustedRunTime", deserialize=deserialize_hhmmss)
    )


@dataclass
class CloudStationRuntime(DataClassDictMixin):
    station_id: int = field(metadata=field_options(alias="stationId"))
    runtime_program_assigned_list: list[CloudProgramRuntime] = field(
        metadata=field_options(alias="runtimeProgramAssignedList"),
        default_factory=list,
    )


@dataclass
class CloudStation(DataClassDictMixin):
    id: int
    station_number: int | None = field(
        default=None, metadata=field_options(alias="stationNumber")
    )
    number: int | None = field(default=None)
    name: str | None = field(default=None)
    terminal: int | None = field(default=None)


@dataclass
class CloudSeasonalAdjust(DataClassDictMixin):
    id: int
    site_id: int = field(metadata=field_options(alias="siteId"))
    seasonal_adjust_pct: int = field(metadata=field_options(alias="seasonalAdjustPct"))
    adjust_type_id: int = field(metadata=field_options(alias="adjustTypeId"))
    jan_adjust: int = field(metadata=field_options(alias="janAdjust"))
    feb_adjust: int = field(metadata=field_options(alias="febAdjust"))
    mar_adjust: int = field(metadata=field_options(alias="marAdjust"))
    apr_adjust: int = field(metadata=field_options(alias="aprAdjust"))
    may_adjust: int = field(metadata=field_options(alias="mayAdjust"))
    jun_adjust: int = field(metadata=field_options(alias="junAdjust"))
    jul_adjust: int = field(metadata=field_options(alias="julAdjust"))
    aug_adjust: int = field(metadata=field_options(alias="augAdjust"))
    sep_adjust: int = field(metadata=field_options(alias="sepAdjust"))
    oct_adjust: int = field(metadata=field_options(alias="octAdjust"))
    nov_adjust: int = field(metadata=field_options(alias="novAdjust"))
    dec_adjust: int = field(metadata=field_options(alias="decAdjust"))


@dataclass
class CloudFlowElement(DataClassDictMixin):
    id: int
    name: str
    flow_rate: float = field(metadata=field_options(alias="flowRate"))
    has_flow_alarm: bool = field(metadata=field_options(alias="hasFlowAlarm"))
    flow_capacity: float = field(metadata=field_options(alias="flowCapacity"))
    satellite_id: int = field(metadata=field_options(alias="satelliteId"))
    description: str | None = None
    ordinal: int | None = None


@dataclass
class CurrentFirmware(DataClassDictMixin):
    id: int
    type: int
    version: str
    site_id: int = field(metadata=field_options(alias="siteID"))
    company_id: int = field(metadata=field_options(alias="companyID"))
    bootloader_version: str = field(metadata=field_options(alias="bootloaderVersion"))
    cic_type: int = field(metadata=field_options(alias="cicType"))
    cic_version: str = field(metadata=field_options(alias="cicVersion"))
    has_mrm: bool = field(metadata=field_options(alias="hasMrm"))


@dataclass
class CloudFirmwareVersions(DataClassDictMixin):
    current: CurrentFirmware
