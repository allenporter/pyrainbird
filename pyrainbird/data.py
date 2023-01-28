"""Data model for rainbird client api."""

import datetime
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Optional

from ical.iter import MergedIterable, SortableItem
from ical.timespan import Timespan
from pydantic import BaseModel, Field, root_validator, validator

from .const import DayOfWeek, ProgramFrequency
from .resources import RAINBIRD_MODELS
from .timeline import ProgramEvent, ProgramTimeline, create_recurrence, ProgramId

_LOGGER = logging.getLogger(__name__)

_MAX_ZONES = 32


@dataclass
class Echo:
    """Echo response from the API."""

    echo: int
    """Return the input command."""

    def __str__(self):
        return "echo: %02X" % self.echo


@dataclass
class CommandSupport:
    """Command support response from the API."""

    support: int
    """Return if the command is supported."""


    echo: int
    """Return the input command."""

    def __str__(self):
        return "command support: %02X, echo: %s" % (self.support, self.echo)


@dataclass
class ModelInfo:
    """Details about capabilities of a specific model."""

    device_id: str
    """The device identifier string."""

    code: str
    """The model code string."""

    name: str
    """The human readable model name."""

    supports_water_budget: bool
    """If the mode supports seasonal adjustment/water budgets."""

    max_programs: int
    """The maximum number of programs supported by the device."""

    max_run_times: int
    """The maximum number of run times supported by the device."""


@dataclass
class ModelAndVersion:
    """Model and version response from the API."""

    model: int
    """The device model number hex code."""

    major: str
    """The major version string."""

    minor: str
    """The minor version string."""

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
    """The controller firmware major version."""

    minor: str
    """The controller firmware minor version."""

    patch: str
    """The controller firmware patch version."""


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
    """Information about stations available in a controller."""

    stations: States
    """Return information about available stations."""

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


class ControllerInfo(BaseModel):
    """Data about the controller settings."""

    station_delay: int = Field(alias="stationDelay", default=0)
    rain_delay: int = Field(alias="rainDelay", default=0)
    rain_sensor: bool = Field(alias="rainSensor", default=False)

    @property
    def delay_days(self) -> int:
        """Return the amount of delay before starting the schedule."""
        return max(self.station_delay, self.rain_delay)


class ZoneDuration(BaseModel):
    """Program runtime for a specific zone."""

    zone: int
    """Zone the program irrigates."""

    duration: datetime.timedelta
    """Runtime of the program in the specified zone."""

    @property
    def name(self) -> str:
        return f"Zone {self.zone}"

    @validator("zone", pre=True)
    def _parse_zone(cls, value: int) -> datetime.timedelta:
        """Parse the zone value."""
        return value + 1

    @validator("duration", pre=True)
    def _parse_duration(cls, value: int) -> datetime.timedelta:
        """Parse the zone duration values."""
        return datetime.timedelta(minutes=value)


class Program(BaseModel):
    """Details about a program.

    The frequency determines which fields of the program are relevant. A
    CUSTOM program looks at days_of_week. A CYCLIC program looks at period.
    ODD/EVEN are odd/even days of the month.
    """

    program: int
    """The program number."""

    frequency: ProgramFrequency
    """Determines how often the program runs."""

    days_of_week: set[DayOfWeek] = Field(alias="daysOfWeekMask", default_factory=set)
    """For a CUSTOM program determines the days of the week."""

    period: Optional[int]
    """For a CYCLIC program determines how often to run."""

    synchro: Optional[int]
    """Days from today before starting the first day of the program."""

    starts: list[datetime.time] = Field(default_factory=list)
    """Time of day the program starts."""

    durations: list[ZoneDuration] = Field(default_factory=list)
    """Durations for run times for each zone."""

    controller_info: Optional[ControllerInfo] = Field(alias="controllerInfo")
    """Information about the controller as input into the programs."""

    @property
    def name(self) -> str:
        """Name of the program."""
        letter = chr(ord("A") + self.program)
        return f"PGM {letter}"

    @property
    def timeline(self) -> ProgramTimeline:
        """Return a timeline of events for the program."""
        return self.timeline_tz(datetime.datetime.now().tzinfo)

    def timeline_tz(self, tzinfo: datetime.tzinfo) -> ProgramTimeline:
        """Return a timeline of events for the program."""
        iters: list[Iterable[SortableItem[Timespan, ProgramEvent]]] = []
        now = datetime.datetime.now(tzinfo)
        for start in self.starts:
            dtstart = now.replace(hour=start.hour, minute=start.minute, second=0)
            iters.append(
                create_recurrence(
                    ProgramId(self.program),
                    self.frequency,
                    dtstart,
                    self.duration,
                    self.synchro,
                    self.days_of_week,
                    self.period,
                    delay_days=self.delay_days,
                ),
            )
        return ProgramTimeline(MergedIterable(iters))

    @property
    def zone_timeline(self) -> ProgramTimeline:
        """Return a timeline of events for the program."""
        iters: list[Iterable[SortableItem[Timespan, ProgramEvent]]] = []
        now = datetime.datetime.now()
        for start in self.starts:
            dtstart = now.replace(hour=start.hour, minute=start.minute, second=0)
            for zone_duration in self.durations:
                iters.append(
                    create_recurrence(
                        ProgramId(self.program, zone_duration.zone),
                        self.frequency,
                        dtstart,
                        zone_duration.duration,
                        self.synchro,
                        self.days_of_week,
                        self.period,
                        delay_days=self.delay_days,
                    )
                )
                dtstart += zone_duration.duration
        return ProgramTimeline(MergedIterable(iters))

    @property
    def duration(self) -> datetime.timedelta:
        """Total duration of the program."""
        total = datetime.timedelta(seconds=0)
        for delta in self.durations:
            total += delta.duration
        return total

    @property
    def delay_days(self) -> int:
        """Return the number of delays programs are delayed."""
        return self.controller_info.delay_days if self.controller_info else 0

    @root_validator(pre=True)
    def _clear_other_fields(cls, values: dict[str, Any]) -> set[DayOfWeek]:
        """Clear fields unrelated to the current frequency."""
        if ProgramFrequency.CUSTOM != values.get("frequency"):
            if "daysOfWeekMask" in values:
                del values["daysOfWeekMask"]
        if ProgramFrequency.CYCLIC != values.get("frequency"):
            if "period" in values:
                del values["period"]
        return values

    @validator("days_of_week", pre=True)
    def _parse_days_of_week(cls, mask: int) -> set[DayOfWeek]:
        """Parse the days of week bitmask to a enum set."""
        result: set[DayOfWeek] = set()
        for day in range(0, 7):
            if mask & (1 << day):
                result.add(DayOfWeek(day))
        return result

    @validator("starts", pre=True)
    def _parse_starts(cls, starts: list[int]) -> set[DayOfWeek]:
        """Parse the days of week bitmask to a enum set."""
        result: list[datetime.time] = []
        for start in starts:
            if start == 65535:
                continue
            result.append(datetime.time(hour=int(start / 60), minute=start % 60))
        return result


class Schedule(BaseModel):
    """Details about program schedules."""

    controller_info: Optional[ControllerInfo] = Field(alias="controllerInfo")
    """Information about the controller used in the schedule."""

    programs: list[Program] = Field(alias="programInfo")
    """Details about the currently scheduled programs."""

    @property
    def timeline(self) -> ProgramTimeline:
        """Return a timeline of all programs."""
        return self.timeline_tz(datetime.datetime.now().tzinfo)

    def timeline_tz(self, tzinfo: datetime.tzinfo) -> ProgramTimeline:
        """Return a timeline of all programs."""
        iters: list[Iterable[SortableItem[Timespan, ProgramEvent]]] = []
        now = datetime.datetime.now(tzinfo)
        for program in self.programs:
            for start in program.starts:
                dtstart = now.replace(hour=start.hour, minute=start.minute, second=0)
                iters.append(
                    create_recurrence(
                        ProgramId(program.program),
                        program.frequency,
                        dtstart,
                        program.duration,
                        program.synchro,
                        program.days_of_week,
                        program.period,
                        delay_days=self.delay_days,
                    )
                )
        return ProgramTimeline(MergedIterable(iters))

    @property
    def delay_days(self) -> int:
        """Return the number of delays programs are delayed."""
        return self.controller_info.delay_days if self.controller_info else 0

    @root_validator(pre=True)
    def _parse_start_info(cls, values: dict[str, Any]):
        """Parse the input values from the response into a usable format."""
        programs = values.get("programStartInfo", [])
        if not programs:
            return values
        for program_start_info in values.get("programStartInfo"):
            program = program_start_info.get("program")
            if program is None:
                continue
            values["programInfo"][program]["starts"] = program_start_info.get(
                "startTime", []
            )
            values["programInfo"][program]["controllerInfo"] = values.get(
                "controllerInfo"
            )
        return values

    @root_validator(pre=True)
    def _parse_durations(cls, values: dict[str, Any]):
        """Parse the input values from the response into a usable format."""
        programs = values.get("programInfo", [])
        if not programs:
            return values
        for program in range(0, len(programs)):
            values["programInfo"][program]["durations"] = []
        for zone_durations in values.get("durations", []):
            zone = zone_durations.get("zone")
            if zone is None:
                continue
            duration_values = zone_durations.get("durations", [])
            if len(duration_values) != len(programs):
                _LOGGER.debug(
                    "Mismatched number of program durations: %d != %d: %s",
                    len(duration_values),
                    len(programs),
                    values,
                )
                continue
            for program in range(0, len(programs)):
                duration = duration_values[program]
                if not duration:
                    continue
                values["programInfo"][program]["durations"].append(
                    {
                        "zone": zone,
                        "duration": duration,
                    }
                )

        return values
