"""Data model for rainbird client api."""

import datetime
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Optional

from pydantic import BaseModel, Field, root_validator

from .resources import RAINBIRD_MODELS

_MAX_ZONES = 32


@dataclass
class Echo:
    """Echo response from the API."""

    echo: int

    def __str__(self):
        return "echo: %02X" % self.echo


@dataclass
class CommandSupport:
    """Command support response from the API."""

    support: int
    echo: int

    def __str__(self):
        return "command support: %02X, echo: %s" % (self.support, self.echo)


@dataclass
class ModelInfo:
    """Details about capabilities of a specific model."""

    device_id: str
    code: str
    name: str
    supports_water_budget: bool
    max_programs: int
    max_run_times: int


@dataclass
class ModelAndVersion:
    """Model and version response from the API."""

    model: int
    """The device model number hex code."""

    major: str
    minor: str

    @property
    def model_code(self) -> str:
        """The device model code string."""
        return self.model_info.code

    @property
    def model_name(self) -> str:
        """The device model name."""
        return self.model_info.name

    @property
    def model_info(self) -> ModelInfo:
        """Return details about a device model capabilities."""
        return ModelInfo(**RAINBIRD_MODELS["%04x" % self.model])

    def __str__(self):
        return "model: %04X (%s), version: %d.%d" % (
            self.model,
            self.model_name,
            self.major,
            self.minor,
        )


@dataclass
class ControllerFirmwareVersion:
    """Controller firmware version."""

    major: str
    minor: str
    patch: str


@dataclass
class States:
    """Rainbird controller response containing a bitmask string e.g. active zones."""

    count: int
    mask: str
    states: tuple

    def __init__(self, mask: str) -> None:
        """Initialize States."""
        self.count = len(mask) * 4
        self.mask = int(mask, 16)
        self.states = ()
        rest = mask
        while rest:
            current = int(rest[:2], 16)
            rest = rest[2:]
            for i in range(0, 8):
                self.states = self.states + (bool((1 << i) & current),)

    def active(self, number: int) -> bool:
        """Return true if the specified zone is active."""
        if number > len(self.states):
            return False
        return self.states[number - 1]

    @property
    def active_set(self):
        """Return the set of active zones."""
        return {number for number in range(1, _MAX_ZONES + 1) if self.active(number)}

    def __str__(self):
        result = ()
        for i in range(0, self.count):
            result += ("%d:%d" % (i + 1, 1 if self.states[i] else 0),)
        return "states: %s" % ", ".join(result)


@dataclass
class AvailableStations:

    stations: States

    def __init__(self, mask: str):
        self.stations = States(mask)

    @property
    def active_set(self):
        """Return the set of active zones."""
        return self.stations.active_set

    def __str__(self):
        return "available stations: %X, %s" % (
            self.stations.mask,
            super(AvailableStations, self).__str__(),
        )


@dataclass
class WaterBudget:
    program: int
    adjust: int


class WifiParams(BaseModel):
    """Wifi parameters for the device."""

    mac_address: Optional[str] = Field(alias="macAddress")
    """The mac address for the device, also referred to as the stick id."""

    local_ip_address: Optional[str] = Field(alias="localIpAddress")
    local_netmask: Optional[str] = Field(alias="localNetmask")
    local_gateway: Optional[str] = Field(alias="localGateway")
    rssi: Optional[int]
    wifi_ssid: Optional[str] = Field(alias="wifiSsid")
    wifi_password: Optional[str] = Field(alias="wifiPassword")
    wifi_security: Optional[str] = Field(alias="wifiSecurity")
    ap_timeout_no_lan: Optional[int] = Field(alias="apTimeoutNoLan")
    ap_timeout_idle: Optional[int] = Field(alias="apTimeoutIdle")
    ap_security: Optional[str] = Field(alias="apSecurity")
    sick_version: Optional[str] = Field(alias="stickVersion")


class SoilType(IntEnum):
    """Soil type."""

    NONE = 0
    CLAY = 1
    SAND = 2
    OTHER = 3


class ProgramInfo(BaseModel):
    """Program information for the device.

    The values are repeated once for each program.
    """

    soil_types: list[SoilType] = Field(default_factory=list, alias="SoilTypes")
    flow_rates: list[int] = Field(default_factory=list, alias="FlowRates")
    flow_units: list[int] = Field(default_factory=list, alias="FlowUnits")

    @root_validator(pre=True)
    def _soil_type(cls, values: dict[str, Any]):
        """Validate different ways the SoilTypes parameter is handled."""
        if soil_type := values.get("soilTypes"):
            values["SoilTypes"] = soil_type
        return values


class Settings(BaseModel):
    """Settings for the device."""

    num_programs: int = Field(alias="numPrograms")
    program_opt_out_mask: str = Field(alias="programOptOutMask")
    global_disable: bool = Field(alias="globalDisable")

    code: Optional[str]
    """Zip code for the device."""

    country: Optional[str]
    """Country location of the device."""

    # Program information
    soil_types: list[SoilType] = Field(default_factory=list, alias="SoilTypes")
    flow_rates: list[int] = Field(default_factory=list, alias="FlowRates")
    flow_units: list[int] = Field(default_factory=list, alias="FlowUnits")

    @root_validator(pre=True)
    def _soil_type(cls, values: dict[str, Any]):
        """Validate different ways the SoilTypes parameter is handled."""
        if soil_type := values.get("soilTypes"):
            values["SoilTypes"] = soil_type
        return values


class WeatherAdjustmentMask(BaseModel):
    """Weather adjustment mask response."""

    num_programs: int = Field(alias="numPrograms")
    program_opt_out_mask: str = Field(alias="programOptOutMask")
    global_disable: bool = Field(alias="globalDisable")


class ZipCode(BaseModel):
    """Get the zip code of the device."""

    code: Optional[str]
    """Zip code for the device."""

    country: Optional[str]
    """Country location of the device."""


class ScheduleAndSettings:
    """Schedule and settings form the cloud API."""

    def __init__(self, status: Optional[str], settings: Optional[Settings]) -> None:
        self._status = status
        self._settings = settings

    @property
    def status(self) -> str:
        """Return device status."""
        return self._status

    @property
    def settings(self) -> Optional[Settings]:
        """Return device settings."""
        return self._settings

    @classmethod
    def parse_obj(cls, data: dict[str, Any]):
        """Parse a ScheduleAndSettings from an API response."""
        status = data.get("status", None)
        settings = Settings.parse_obj(data["settings"]) if "settings" in data else None
        return ScheduleAndSettings(status, settings)


class Controller(BaseModel):
    """Settings for the controller."""

    available_stations: list[int] = Field(
        alias="availableStations", default_factory=list
    )
    custom_name: Optional[str] = Field(alias="customName")
    custom_program_names: dict[str, str] = Field(
        alias="customProgramNames", default_factory=dict
    )
    custom_station_names: dict[str, str] = Field(
        alias="customStationNames", default_factory=dict
    )


class Forecast(BaseModel):
    """Weather forecast data from the cloud API."""

    date_time: Optional[int] = Field(alias="dateTime")
    icon: Optional[str]
    description: Optional[str]
    high: Optional[int]
    low: Optional[int]
    chance_of_rain: Optional[int]
    precip: Optional[float]


class Weather(BaseModel):
    """Weather settings from the cloud API."""

    city: Optional[str]
    forecast: list[Forecast] = Field(default_factory=list)
    location: Optional[str]
    time_zone_id: Optional[str] = Field(alias="timeZoneId")
    time_zone_raw_offset: Optional[str] = Field(alias="timeZoneRawOffset")


class WeatherAndStatus(BaseModel):
    """Weather and status from the cloud API."""

    stick_id: Optional[str] = Field(alias="StickId")
    controller: Optional[Controller] = Field(alias="Controller")
    forecasted_rain: Optional[dict[str, Any]] = Field(alias="ForecastedRain")
    weather: Optional[Weather] = Field(alias="Weather")


class NetworkStatus(BaseModel):
    """Get the device network status."""

    network_up: bool = Field(alias="networkUp")
    internet_up: bool = Field(alias="internetUp")


class ServerMode(BaseModel):
    """Details about the device server connection."""

    server_mode: bool = Field(alias="serverMode")
    check_in_interval: int = Field(alias="checkInInterval")
    server_url: str = Field(alias="serverUrl")
    relay_timeout: int = Field(alias="relayTimeout")
    missed_checkins: int = Field(alias="missedCheckins")


class ControllerState(BaseModel):
    """Details about the controller state."""

    delay_setting: int = Field(alias="delaySetting")
    """Number of days that irrigation is paused."""

    sensor_state: int = Field(alias="sensorState")
    """Rain sensor status."""

    irrigation_state: int = Field(alias="irrigationState")
    """State of irrigation."""

    seasonal_adjust: int = Field(alias="seasonalAdjust")
    remaining_runtime: int = Field(alias="remainingRuntime")

    # TODO: Likely need to make this a mask w/ States
    active_station: int = Field(alias="activeStation")

    device_time: datetime.datetime

    @root_validator(pre=True)
    def _device_time(cls, values: dict[str, Any]):
        """Validate different ways the SoilTypes parameter is handled."""
        for field in {"year", "month", "day", "hour", "minute", "second"}:
            if field not in values:
                raise ValueError(f"Missing field '{field}' in values")
        values["device_time"] = datetime.datetime(
            int(values["year"]),
            int(values["month"]),
            int(values["day"]),
            int(values["hour"]),
            int(values["minute"]),
            int(values["second"]),
        )
        return values
