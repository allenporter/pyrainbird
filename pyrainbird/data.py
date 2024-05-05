"""Data model for rainbird client api."""

import datetime
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from ical.iter import MergedIterable, SortableItem
from ical.timespan import Timespan
from mashumaro.codecs.yaml import yaml_decode, yaml_encode
from mashumaro import DataClassDictMixin, field_options
from mashumaro.config import BaseConfig
from mashumaro.types import SerializationStrategy

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

    retries: bool = False
    """If device busy errors should be retried"""


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
        key = f"{self.model:04x}"
        data = RAINBIRD_MODELS.get(key, RAINBIRD_MODELS["UNKNOWN"])
        return ModelInfo(**data)

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


@dataclass
class WifiParams(DataClassDictMixin):
    """Wifi parameters for the device."""

    mac_address: Optional[str] = field(metadata=field_options(alias="macAddress"))
    """The mac address for the device, also referred to as the stick id."""

    local_ip_address: Optional[str] = field(metadata=field_options(alias="localIpAddress"))
    local_netmask: Optional[str] = field(metadata=field_options(alias="localNetmask"))
    local_gateway: Optional[str] = field(metadata=field_options(alias="localGateway"))
    rssi: Optional[int]
    wifi_ssid: Optional[str] = field(metadata=field_options(alias="wifiSsid"))
    wifi_password: Optional[str] = field(metadata=field_options(alias="wifiPassword"))
    wifi_security: Optional[str] = field(metadata=field_options(alias="wifiSecurity"))
    ap_timeout_no_lan: Optional[int] = field(metadata=field_options(alias="apTimeoutNoLan"))
    ap_timeout_idle: Optional[int] = field(metadata=field_options(alias="apTimeoutIdle"))
    ap_security: Optional[str] = field(metadata=field_options(alias="apSecurity"))
    sick_version: Optional[str] = field(metadata=field_options(alias="stickVersion"))


class SoilType(IntEnum):
    """Soil type."""

    NONE = 0
    CLAY = 1
    SAND = 2
    OTHER = 3


@dataclass
class ProgramInfo(DataClassDictMixin):
    """Program information for the device.

    The values are repeated once for each program.
    """

    soil_types: list[SoilType] = field(default_factory=list, metadata=field_options(alias="SoilTypes"))
    flow_rates: list[int] = field(default_factory=list, metadata=field_options(alias="FlowRates"))
    flow_units: list[int] = field(default_factory=list, metadata=field_options(alias="FlowUnits"))

    @classmethod
    def __pre_deserialize__(cls, values: dict[Any, Any]) -> dict[Any, Any]:
        if soil_type := values.get("soilTypes"):
            values["SoilTypes"] = soil_type
        return values


@dataclass
class Settings(DataClassDictMixin):
    """Settings for the device."""

    num_programs: int = field(metadata=field_options(alias="numPrograms"))
    program_opt_out_mask: str = field(metadata=field_options(alias="programOptOutMask"))
    global_disable: bool = field(metadata=field_options(alias="globalDisable"))

    code: Optional[str]
    """Zip code for the device."""

    country: Optional[str]
    """Country location of the device."""

    # Program information
    soil_types: list[SoilType] = field(default_factory=list, metadata=field_options(alias="SoilTypes"))
    flow_rates: list[int] = field(default_factory=list, metadata=field_options(alias="FlowRates"))
    flow_units: list[int] = field(default_factory=list, metadata=field_options(alias="FlowUnits"))

    @classmethod
    def __pre_deserialize__(cls, values: dict[Any, Any]) -> dict[Any, Any]:
        if soil_type := values.get("soilTypes"):
            values["SoilTypes"] = soil_type
        return values


@dataclass
class WeatherAdjustmentMask(DataClassDictMixin):
    """Weather adjustment mask response."""

    num_programs: int = field(metadata=field_options(alias="numPrograms"))
    program_opt_out_mask: str = field(metadata=field_options(alias="programOptOutMask"))
    global_disable: bool = field(metadata=field_options(alias="globalDisable"))


@dataclass
class ZipCode(DataClassDictMixin):
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
    def from_dict(cls, data: dict[str, Any]):
        """Parse a ScheduleAndSettings from an API response."""
        status = data.get("status", None)
        settings = Settings.from_dict(data["settings"]) if "settings" in data else None
        return ScheduleAndSettings(status, settings)


@dataclass
class Controller(DataClassDictMixin):
    """Settings for the controller."""

    available_stations: list[int] = field(
        metadata=field_options(alias="availableStations"), default_factory=list
    )
    custom_name: Optional[str] = field(metadata=field_options(alias="customName"), default=None)
    custom_program_names: dict[str, str] = field(
        metadata=field_options(alias="customProgramNames"), default_factory=dict
    )
    custom_station_names: dict[str, str] = field(
        metadata=field_options(alias="customStationNames"), default_factory=dict
    )


@dataclass
class Forecast(DataClassDictMixin):
    """Weather forecast data from the cloud API."""

    date_time: Optional[int] = field(metadata=field_options(alias="dateTime"))
    icon: Optional[str]
    description: Optional[str]
    high: Optional[int]
    low: Optional[int]
    chance_of_rain: Optional[int]
    precip: Optional[float]


@dataclass
class Weather(DataClassDictMixin):
    """Weather settings from the cloud API."""

    city: Optional[str]
    forecast: list[Forecast] = field(default_factory=list)
    location: Optional[str] = None
    time_zone_id: Optional[str] = field(metadata=field_options(alias="timeZoneId"), default=None)
    time_zone_raw_offset: Optional[str] = field(metadata=field_options(alias="timeZoneRawOffset"), default=None)


@dataclass
class WeatherAndStatus(DataClassDictMixin):
    """Weather and status from the cloud API."""

    stick_id: Optional[str] = field(metadata=field_options(alias="StickId"))
    controller: Optional[Controller] = field(metadata=field_options(alias="Controller"))
    forecasted_rain: Optional[dict[str, Any]] = field(metadata=field_options(alias="ForecastedRain"))
    weather: Optional[Weather] = field(metadata=field_options(alias="Weather"))


@dataclass
class NetworkStatus(DataClassDictMixin):
    """Get the device network status."""

    network_up: bool = field(metadata=field_options(alias="networkUp"))
    internet_up: bool = field(metadata=field_options(alias="internetUp"))


@dataclass
class ServerMode(DataClassDictMixin):
    """Details about the device server connection."""

    server_mode: bool = field(metadata=field_options(alias="serverMode"))
    check_in_interval: int = field(metadata=field_options(alias="checkInInterval"))
    server_url: str = field(metadata=field_options(alias="serverUrl"))
    relay_timeout: int = field(metadata=field_options(alias="relayTimeout"))
    missed_checkins: int = field(metadata=field_options(alias="missedCheckins"))


class DeviceTime(SerializationStrategy):
    """Validate different ways the device time parameter is handled."""

    # def serialize(self, value: datetime) -> str:
    #     return value.strftime(self.fmt)

    def deserialize(self, values: dict[str, Any]) -> datetime.datetime:
        """Deserialize the device time fields."""
        for field in {"year", "month", "day", "hour", "minute", "second"}:
            if field not in values:
                raise ValueError(f"Missing field '{field}' in values")
        return datetime.datetime(
            int(values["year"]),
            int(values["month"]),
            int(values["day"]),
            int(values["hour"]),
            int(values["minute"]),
            int(values["second"]),
        )

@dataclass
class ControllerState(DataClassDictMixin):
    """Details about the controller state."""

    delay_setting: int = field(metadata=field_options(alias="delaySetting"))
    """Number of days that irrigation is paused."""

    sensor_state: int = field(metadata=field_options(alias="sensorState"))
    """Rain sensor status."""

    irrigation_state: int = field(metadata=field_options(alias="irrigationState"))
    """State of irrigation."""

    seasonal_adjust: int = field(metadata=field_options(alias="seasonalAdjust"))
    remaining_runtime: int = field(metadata=field_options(alias="remainingRuntime"))

    # TODO: Likely need to make this a mask w/ States
    active_station: int = field(metadata=field_options(alias="activeStation"))

    device_time: datetime.datetime = field(metadata=field_options(serialization_strategy=DeviceTime()))

    @classmethod
    def __pre_deserialize__(cls, d: dict[Any, Any]) -> dict[Any, Any]:
        d["device_time"] = {
            k: d[k]
            for k in ("year", "month", "day", "hour", "minute", "second")
        }
        return d


@dataclass
class ControllerInfo(DataClassDictMixin):
    """Data about the controller settings."""

    station_delay: int = field(metadata=field_options(alias="stationDelay"), default=0)
    rain_delay: int = field(metadata=field_options(alias="rainDelay"), default=0)
    rain_sensor: bool = field(metadata=field_options(alias="rainSensor"), default=False)

    @property
    def delay_days(self) -> int:
        """Return the amount of delay before starting the schedule."""
        return max(self.station_delay, self.rain_delay)


@dataclass
class ZoneDuration(DataClassDictMixin):
    """Program runtime for a specific zone."""

    zone: int
    """Zone the program irrigates."""

    duration: datetime.timedelta
    """Runtime of the program in the specified zone."""

    @property
    def name(self) -> str:
        return f"Zone {self.zone}"

    @classmethod
    def __pre_deserialize__(cls, values: dict[Any, Any]) -> dict[Any, Any]:
        if duration := values.get("duration"):
            values["duration"] = duration * 60  #datetime.timedelta(minutes=duration)
        return values


class TimeSerializationStrategy(SerializationStrategy):
    """Validate different ways the device time parameter is handled."""

    def serialize(self, value: Any) -> Any:
        raise ValueError("Serialize not implemented")

    def deserialize(self, starts: list[int]) -> list[datetime.time]:
        """Deserialize the device time fields."""
        result: list[datetime.time] = []
        for start in starts:
            if start == 65535:
                continue
            result.append(datetime.time(hour=int(start / 60), minute=start % 60))
        return result




class DayOfWeekSerializationStrategy(SerializationStrategy):
    """Validate different ways the device time parameter is handled."""

    def serialize(self, value: Any) -> str:
        raise ValueError("Serialization not implemented")

    def deserialize(self, mask: int) -> list[DayOfWeek]:
        """Deserialize the device time fields."""
        _LOGGER.debug("DayOfWeekSerializationStrategy=%s", mask)
        result: set[DayOfWeek] = set()
        for day in range(0, 7):
            if mask & (1 << day):
                result.add(DayOfWeek(day))
        return result


@dataclass
class Program(DataClassDictMixin):
    """Details about a program.

    The frequency determines which fields of the program are relevant. A
    CUSTOM program looks at days_of_week. A CYCLIC program looks at period.
    ODD/EVEN are odd/even days of the month.
    """

    program: int
    """The program number."""

    frequency: ProgramFrequency
    """Determines how often the program runs."""

    days_of_week: set[DayOfWeek] = field(metadata=field_options(alias="daysOfWeekMask", serialization_strategy=DayOfWeekSerializationStrategy()), default_factory=set)
    """For a CUSTOM program determines the days of the week."""

    period: Optional[int] = None
    """For a CYCLIC program determines how often to run."""

    synchro: Optional[int] = None
    """Days from today before starting the first day of the program."""

    starts: list[datetime.time] = field(default_factory=list, metadata=field_options(serialization_strategy=TimeSerializationStrategy()))
    """Time of day the program starts."""

    durations: list[ZoneDuration] = field(default_factory=list)
    """Durations for run times for each zone."""

    controller_info: Optional[ControllerInfo] = field(metadata=field_options(alias="controllerInfo"), default=None)
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

    def __post_init__(self):
        if self.frequency != ProgramFrequency.CUSTOM:
            self.days_of_week = set()
        if self.frequency != ProgramFrequency.CYCLIC:
            self.period = None



@dataclass
class Schedule(DataClassDictMixin):
    """Details about program schedules."""

    controller_info: Optional[ControllerInfo] = field(metadata=field_options(alias="controllerInfo"))
    """Information about the controller used in the schedule."""

    programs: list[Program] = field(metadata=field_options(alias="programInfo"))
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

    @classmethod
    def __pre_deserialize__(cls, values: dict[Any, Any]) -> dict[Any, Any]:
        """Parse the input values from the response into a usable format."""
        programs = values.get("programStartInfo", [])
        if not programs:
            return values
        for program_start_info in programs:
            program = program_start_info.get("program")
            if program is None:
                continue
            values["programInfo"][program]["starts"] = program_start_info.get(
                "startTime", []
            )
            values["programInfo"][program]["controllerInfo"] = values.get(
                "controllerInfo"
            )
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
                        "zone": zone + 1,
                        "duration": duration,
                    }
                )
        return values
