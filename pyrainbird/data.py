"""Data model for rainbird client api."""

from typing import Any, Optional

from pydantic import BaseModel, Field

from .resources import RAINBIRD_MODELS

_DEFAULT_PAGE = 0


class Pageable(object):
    def __init__(self, page=_DEFAULT_PAGE):
        self.page = page

    def __hash__(self):
        return hash(self.page)

    def __eq__(self, o):
        return isinstance(o, Pageable) and self.page == o.page

    def __ne__(self, o):
        return not self.__eq__(o)

    def __str__(self):
        return "page: %d" % self.page


class Echo(object):
    def __init__(self, echo):
        self.echo = echo

    def __hash__(self):
        return hash(self.echo)

    def __eq__(self, o):
        return isinstance(o, Echo) and self.echo == o.echo

    def __ne__(self, o):
        return not self.__eq__(o)

    def __str__(self):
        return "echo: %02X" % self.echo


class CommandSupport(Echo):
    def __init__(self, support, echo=0):
        super(CommandSupport, self).__init__(echo)
        self.support = support

    def __eq__(self, o):
        return (
            super(CommandSupport, self).__eq__(o)
            and isinstance(o, CommandSupport)
            and o.support == self.support
        )

    def __ne__(self, o):
        return not self.__eq__(o)

    def __hash__(self):
        return hash((super(CommandSupport, self).__hash__(), self.support))

    def __str__(self):
        return "command support: %02X, %s" % (
            self.support,
            super(CommandSupport, self).__str__(),
        )


class ModelAndVersion(object):
    def __init__(self, model, revMajor, revMinor):
        self.model = model
        self.major = revMajor
        self.minor = revMinor
        self.model_code = RAINBIRD_MODELS[self.model][0]
        self.model_name = RAINBIRD_MODELS[self.model][2]

    def __hash__(self):
        return hash((self.model, self.major, self.minor))

    def __eq__(self, o):
        return (
            isinstance(o, ModelAndVersion)
            and self.model == o.model
            and self.major == o.major
            and self.minor == o.minor
        )

    def __ne__(self, o):
        return not self.__eq__(o)

    def __str__(self):
        return "model: %04X, version: %d.%d" % (
            self.model,
            self.major,
            self.minor,
        )


class States(object):
    def __init__(self, mask="0000"):
        self.count = len(mask) * 4
        self.mask = int(mask, 16)
        self.states = ()
        rest = mask
        while rest:
            current = int(rest[:2], 16)
            rest = rest[2:]
            for i in range(0, 8):
                self.states = self.states + (bool((1 << i) & current),)

    def active(self, number):
        return self.states[number - 1]

    def __hash__(self):
        return hash((self.count, self.mask, self.states))

    def __eq__(self, o):
        return (
            isinstance(o, States)
            and self.count == o.count
            and self.mask == o.mask
            and self.states == o.states
        )

    def __ne__(self, o):
        return not self.__eq__(o)

    def __str__(self):
        result = ()
        for i in range(0, self.count):
            result += ("%d:%d" % (i + 1, 1 if self.states[i] else 0),)
        return "states: %s" % ", ".join(result)


class AvailableStations(Pageable):
    def __init__(self, mask, page=_DEFAULT_PAGE):
        super(AvailableStations, self).__init__(page)
        self.stations = States(mask)

    def __hash__(self):
        return hash((super(AvailableStations, self).__hash__(), self.stations))

    def __eq__(self, o):
        return (
            super(AvailableStations, self).__eq__(o)
            and isinstance(o, AvailableStations)
            and self.stations == o.stations
        )

    def __ne__(self, o):
        return not self.__eq__(o)

    def __str__(self):
        return "available stations: %X, %s" % (
            self.stations.mask,
            super(AvailableStations, self).__str__(),
        )


class WaterBudget(object):
    def __init__(self, program, adjust):
        self.program = program
        self.adjust = adjust

    def __hash__(self):
        return hash((self.program, self.adjust))

    def __eq__(self, o):
        return (
            isinstance(o, WaterBudget)
            and self.program == o.program
            and self.adjust == o.adjust
        )

    def __ne__(self, o):
        return not self.__eq__(o)

    def __str__(self):
        return "water budget: program: %d, hi: %02X, lo: %02X" % (
            self.program,
            self.adjust,
        )


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


class ProgramInfo(BaseModel):
    """Program information for the device."""

    soil_types: list[int] = Field(default_factory=list, alias="SoilTypes")
    flow_rates: list[int] = Field(default_factory=list, alias="FlowRates")
    flow_units: list[int] = Field(default_factory=list, alias="FlowUnits")


class Settings(BaseModel):
    """Settings for the device."""

    num_programs: int = Field(alias="numPrograms")
    program_opt_out_mask: str = Field(alias="programOptOutMask")

    code: Optional[str]
    """Zip code for the device."""

    country: Optional[str]
    """Country location of the device."""

    global_disable: bool = Field(alias="globalDisable")

    # Program information
    soil_types: list[int] = Field(default_factory=list, alias="soilTypes")
    flow_rates: list[str] = Field(default_factory=list, alias="FlowRates")
    flow_units: list[str] = Field(default_factory=list, alias="FlowUnits")


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
