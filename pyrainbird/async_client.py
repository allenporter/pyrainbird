"""An asyncio based client library for Rain Bird.

You may create an `AsyncRainbirdController` with the `CreateController` call that
accepts the hostname and password of the Rain Bird controller.

Most API calls are fairly low level with thin response wrappers that are data classes,
though some static data about the device may have the underlying calls cached.

Note that in general the Rain Bird device can only communicate with one client at
a time and may raise exceptions when the device is busy. Keep this in mind when polling
and querying the device.
"""

import datetime
import logging
from collections.abc import Callable
from http import HTTPStatus
from typing import Any, TypeVar, Union
from urllib.parse import urlparse

import aiohttp
from aiohttp.client_exceptions import ClientError, ClientResponseError
from aiohttp_retry import RetryClient, RetryOptions, JitterRetry


from . import encryption, rainbird
from .data import (
    AvailableStations,
    ControllerFirmwareVersion,
    ControllerState,
    ModelAndVersion,
    NetworkStatus,
    ProgramInfo,
    Schedule,
    ScheduleAndSettings,
    ServerMode,
    Settings,
    States,
    WaterBudget,
    WeatherAdjustmentMask,
    WeatherAndStatus,
    WifiParams,
    ZipCode,
)
from .exceptions import (
    RainbirdApiException,
    RainbirdAuthException,
    RainbirdDeviceBusyException,
)
from .resources import LENGTH, RAINBIRD_COMMANDS, RESPONSE

__all__ = [
    "CreateController",
    "AsyncRainbirdController",
]

_LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


HEAD = {
    "Accept-Language": "en",
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": "RainBird/2.0 CFNetwork/811.5.4 Darwin/16.7.0",
    "Accept": "*/*",
    "Connection": "keep-alive",
    "Content-Type": "application/octet-stream",
}
DATA = "data"
CLOUD_API_URL = "http://rdz-rbcloud.rainbird.com/phone-api"

# In general, these devices can handle only one in flight request at a time
# otherwise return a 503. The caller is expected to follow that, however ESP
# ME devices also seem to return 503s more regularly than other devices so we
# include retry behavior for them. We only retry the specific device busy error.
START_TIMEOUT = 1.0
ATTEMPTS = 3


def _retry_delay() -> float:
    return START_TIMEOUT


def _retry_attempts() -> int:
    return ATTEMPTS


def _device_busy_retry() -> JitterRetry:
    return JitterRetry(
        attempts=_retry_attempts(),
        start_timeout=_retry_delay(),
        statuses=set([HTTPStatus.SERVICE_UNAVAILABLE.value]),
        retry_all_server_errors=False,
    )


class AsyncRainbirdClient:
    """An asyncio rainbird client.

    This is used by the controller and not expected to be used directly.
    """

    def __init__(
        self,
        websession: aiohttp.ClientSession,
        host: str,
        password: Union[str, None],
    ) -> None:
        self._websession = websession
        self._host = host
        parsed = urlparse(host)
        if parsed.scheme in {"http", "https"}:
            if parsed.path:
                self._url = host
            else:
                self._url = f"{host}/stick"
        elif host.startswith("/"):
            self._url = host
        else:
            self._url = f"http://{host}/stick"
        self._password = password
        self._coder = encryption.PayloadCoder(password, _LOGGER)

    def with_retry_options(self, retry_options: RetryOptions) -> "AsyncRainbirdClient":  # type: ignore[valid-type]
        """Create a new AsyncRainbirdClient with retry options."""
        return AsyncRainbirdClient(
            RetryClient(client_session=self._websession, retry_options=retry_options),  # type: ignore[arg-type]
            self._host,
            self._password,
        )

    async def request(
        self, method: str, params: Union[dict[str, Any], None] = None
    ) -> dict[str, Any]:
        """Send a request for any command."""
        payload = self._coder.encode_command(method, params or {})
        try:
            resp = await self._websession.request(
                "post", self._url, data=payload, headers=HEAD
            )
            resp.raise_for_status()
        except ClientResponseError as err:
            _LOGGER.debug("Error response from Rain Bird device: %s", err)
            if err.status == HTTPStatus.SERVICE_UNAVAILABLE:
                raise RainbirdDeviceBusyException(
                    "Rain Bird device is busy; Wait and try again"
                ) from err
            if err.status == HTTPStatus.FORBIDDEN:
                raise RainbirdAuthException(
                    "Rain Bird device denied authentication; Incorrect Password?"
                ) from err
            raise RainbirdApiException("Rain Bird responded with an error")
        except ClientError as err:
            _LOGGER.debug("Error communicating with Rain Bird device: %s", err)
            raise RainbirdApiException(
                "Error communicating with Rain Bird device"
            ) from err
        content = await resp.read()
        return self._coder.decode_command(content)  # type: ignore


def CreateController(
    websession: aiohttp.ClientSession, host: str, password: str
) -> "AsyncRainbirdController":
    """Create an AsyncRainbirdController."""
    local_client = AsyncRainbirdClient(websession, host, password)
    cloud_client = AsyncRainbirdClient(websession, CLOUD_API_URL, None)
    return AsyncRainbirdController(local_client, cloud_client)


class AsyncRainbirdController:
    """Rainbird controller that uses asyncio."""

    def __init__(
        self,
        local_client: AsyncRainbirdClient,
        cloud_client: AsyncRainbirdClient | None = None,
    ) -> None:
        """Initialize AsyncRainbirdController."""
        self._local_client = local_client
        self._cloud_client = cloud_client
        self._cache: dict[str, Any] = {}
        self._model: ModelAndVersion | None = None

    async def get_model_and_version(self) -> ModelAndVersion:
        """Return the model and version."""
        response = await self._cacheable_command(
            lambda response: ModelAndVersion(
                response["modelID"],
                response["protocolRevisionMajor"],
                response["protocolRevisionMinor"],
            ),
            "ModelAndVersionRequest",
        )
        if self._model is None:
            self._model = response
            if self._model.model_info.retries:
                self._local_client = self._local_client.with_retry_options(
                    _device_busy_retry()
                )
        return response

    async def get_available_stations(self) -> AvailableStations:
        """Get the available stations."""
        mask = (
            "%%0%dX"
            % RAINBIRD_COMMANDS["AvailableStationsResponse"]["setStations"][LENGTH]
        )
        return await self._cacheable_command(
            lambda resp: AvailableStations(mask % resp["setStations"]),
            "AvailableStationsRequest",
            0,
        )

    async def get_serial_number(self) -> str:
        """Get the device serial number."""
        try:
            return await self._cacheable_command(
                lambda resp: resp["serialNumber"], "SerialNumberRequest"
            )
        except RainbirdApiException as err:
            _LOGGER.debug("Error while fetching serial number: %s", err)
            raise

    async def get_current_time(self) -> datetime.time:
        """Get the device current time."""
        return await self._process_command(
            lambda resp: datetime.time(resp["hour"], resp["minute"], resp["second"]),
            "CurrentTimeRequest",
        )

    async def set_current_time(self, value: datetime.time) -> None:
        """Set the device current time."""
        await self._process_command(
            lambda resp: True,
            "SetCurrentTimeRequest",
            value.hour,
            value.minute,
            value.second,
        )

    async def get_current_date(self) -> datetime.date:
        """Get the device current date."""
        return await self._process_command(
            lambda resp: datetime.date(resp["year"], resp["month"], resp["day"]),
            "CurrentDateRequest",
        )

    async def set_current_date(self, value: datetime.date) -> None:
        """Set the device current date."""
        await self._process_command(
            lambda resp: True,
            "SetCurrentDateRequest",
            value.day,
            value.month,
            value.year,
        )

    async def get_wifi_params(self) -> WifiParams:
        """Return wifi parameters and other settings."""
        try:
            result = await self._local_client.request("getWifiParams")
        except RainbirdApiException as err:
            _LOGGER.debug("Error while fetching get_wifi_params: %s", err)
            raise
        return WifiParams.from_dict(result)

    async def get_settings(self) -> Settings:
        """Return a combined set of device settings."""
        result = await self._local_client.request("getSettings")
        return Settings.from_dict(result)

    async def get_weather_adjustment_mask(self) -> WeatherAdjustmentMask:
        """Return the weather adjustment mask, subset of the settings."""
        result = await self._local_client.request("getWeatherAdjustmentMask")
        return WeatherAdjustmentMask.from_dict(result)

    async def get_zip_code(self) -> ZipCode:
        """Return zip code and location, a subset of the settings."""
        result = await self._local_client.request("getZipCode")
        return ZipCode.from_dict(result)

    async def get_program_info(self) -> ProgramInfo:
        """Return program information, a subset of the settings."""
        result = await self._local_client.request("getProgramInfo")
        return ProgramInfo.from_dict(result)

    async def get_network_status(self) -> NetworkStatus:
        """Return the device network status."""
        result = await self._local_client.request("getNetworkStatus")
        return NetworkStatus.from_dict(result)

    async def get_server_mode(self) -> ServerMode:
        """Return details about the device server setup."""
        result = await self._local_client.request("getServerMode")
        return ServerMode.from_dict(result)

    async def water_budget(self, budget) -> WaterBudget:
        """Return the water budget."""
        return await self._process_command(
            lambda resp: WaterBudget(resp["programCode"], resp["seasonalAdjust"]),
            "WaterBudgetRequest",
            budget,
        )

    async def get_rain_sensor_state(self) -> bool:
        """Get the current state for the rain sensor."""
        return await self._process_command(
            lambda resp: bool(resp["sensorState"]),
            "CurrentRainSensorStateRequest",
        )

    async def get_zone_states(self) -> States:
        """Return the current state of all zones."""
        mask = (
            "%%0%dX"
            % RAINBIRD_COMMANDS["CurrentStationsActiveResponse"]["activeStations"][
                LENGTH
            ]
        )
        return await self._process_command(
            lambda resp: States((mask % resp["activeStations"])),
            "CurrentStationsActiveRequest",
            0,
        )

    async def get_zone_state(self, zone: int) -> bool:
        """Return the current state of the zone."""
        states = await self.get_zone_states()
        return states.active(zone)

    async def set_program(self, program: int) -> None:
        """Start a program."""
        await self._process_command(
            lambda resp: True, "ManuallyRunProgramRequest", program
        )

    async def test_zone(self, zone: int) -> None:
        """Test a zone."""
        await self._process_command(lambda resp: True, "TestStationsRequest", zone)

    async def irrigate_zone(self, zone: int, minutes: int) -> None:
        """Send the irrigate command."""
        await self._process_command(
            lambda resp: True, "ManuallyRunStationRequest", zone, minutes
        )

    async def stop_irrigation(self) -> None:
        """Send the stop command."""
        await self._process_command(lambda resp: True, "StopIrrigationRequest")

    async def get_rain_delay(self) -> int:
        """Return the current rain delay value."""
        return await self._process_command(
            lambda resp: resp["delaySetting"], "RainDelayGetRequest"
        )

    async def set_rain_delay(self, days: int) -> None:
        """Set the rain delay value in days."""
        await self._process_command(lambda resp: True, "RainDelaySetRequest", days)

    async def advance_zone(self, param: int) -> None:
        """Advance to the specified zone."""
        await self._process_command(lambda resp: True, "AdvanceStationRequest", param)

    async def get_current_irrigation(self) -> bool:
        """Return True if the irrigation state is on."""
        return await self._process_command(
            lambda resp: bool(resp["irrigationState"]),
            "CurrentIrrigationStateRequest",
        )

    async def get_schedule_and_settings(self, stick_id: str) -> ScheduleAndSettings:
        """Request the schedule and settings from the cloud."""
        if not self._cloud_client:
            raise ValueError("Cloud client not configured")
        result = await self._cloud_client.request(
            "requestScheduleAndSettings", {"StickId": stick_id}
        )
        return ScheduleAndSettings.from_dict(result)

    async def get_weather_and_status(
        self, stick_id: str, country: str, zip_code: str
    ) -> WeatherAndStatus:
        """Request the weather and status of the device.

        The results include things like custom station names, program names, etc.
        """
        if not self._cloud_client:
            raise ValueError("Cloud client not configured")
        result = await self._cloud_client.request(
            "requestWeatherAndStatus",
            {
                "Country": country,
                "StickId": stick_id,
                "ZipCode": zip_code,
            },
        )
        return WeatherAndStatus.from_dict(result)

    async def get_combined_controller_state(self) -> ControllerState:
        """Return the combined controller state."""
        return await self._process_command(
            lambda resp: ControllerState.from_dict(resp),
            "CombinedControllerStateRequest",
        )

    async def get_controller_firmware_version(self) -> ControllerFirmwareVersion:
        """Return the controller firmware version."""
        return await self._process_command(
            lambda resp: ControllerFirmwareVersion(
                resp["major"], resp["minor"], resp["patch"]
            ),
            "ControllerFirmwareVersionRequest",
        )

    async def get_schedule(self) -> Schedule:
        """Return the device schedule."""

        model = await self.get_model_and_version()
        max_programs = model.model_info.max_programs
        stations = await self.get_available_stations()
        max_stations = min(stations.stations.count, 22)

        commands = ["00"]
        # Program details
        for program in range(0, max_programs):
            commands.append("%04x" % (0x10 | program))
        # Start times
        for program in range(0, max_programs):
            commands.append("%04x" % (0x60 | program))
        # Run times per zone
        _LOGGER.debug("Loading schedule for %d zones", max_stations)
        for zone_page in range(0, int(round(max_stations / 2, 0))):
            commands.append("%04x" % (0x80 | zone_page))
        _LOGGER.debug("Sending schedule commands: %s", commands)
        # Run command serially to avoid overwhelming the controller
        schedule_data: dict[str, Any] = {
            "controllerInfo": {},
            "programInfo": [],
            "programStartInfo": [],
            "durations": [],
        }
        for command in commands:
            result = await self._process_command(
                lambda resp: resp,
                "RetrieveScheduleRequest",
                int(command, 16),
            )
            if not isinstance(result, dict):
                continue
            for key in schedule_data:
                if (value := result.get(key)) is not None:
                    if key == "durations":
                        for entry in value:
                            if (
                                entry.get("zone", 0) + 1
                            ) not in stations.stations.active_set:
                                continue
                            schedule_data[key].append(entry)
                    elif key == "controllerInfo":
                        schedule_data[key].update(value)
                    else:
                        schedule_data[key].append(value)
        return Schedule.from_dict(schedule_data)

    async def get_schedule_command(self, command_code: str) -> dict[str, Any]:
        """Run the schedule command for the specified raw command code."""
        return await self._process_command(
            lambda resp: resp,
            "RetrieveScheduleRequest",
            command_code,
        )

    async def test_command_support(self, command_id: int) -> bool:
        """Debugging command to test if the device supports the specified command."""
        return await self._process_command(
            lambda resp: bool(resp["support"]), "CommandSupportRequest", command_id
        )

    async def test_rpc_support(self, rpc: str) -> dict[str, Any]:
        """Debugging command to test device support for a json RPC method."""
        return await self._local_client.request(rpc)

    async def _tunnelSip(self, data: str, length: int) -> str:
        """Send a tunnelSip request."""
        result = await self._local_client.request(
            "tunnelSip", {DATA: data, LENGTH: length}
        )
        if DATA not in result:
            _LOGGER.error(
                "Rain Bird device reply missing required 'data' field in tunnelSip"
            )
            raise RainbirdApiException("Unexpected response from Rain Bird device")
        return result[DATA]

    async def _process_command(
        self, funct: Callable[[dict[str, Any]], T], command: str, *args
    ) -> T:
        data = rainbird.encode(command, *args)
        _LOGGER.debug("Request (%s): %s", command, str(data))
        command_data = RAINBIRD_COMMANDS[command]
        decrypted_data = await self._tunnelSip(
            data,
            command_data[LENGTH],
        )
        _LOGGER.debug("Response from line: " + str(decrypted_data))
        decoded = rainbird.decode(decrypted_data)
        _LOGGER.debug("Response: %s" % decoded)
        response_code = decrypted_data[:2]
        allowed = set([command_data[RESPONSE]])
        if funct is None:
            allowed.add("00")  # Allow NACK
        if response_code not in allowed:
            _LOGGER.error(
                "Request (%s) failed with wrong response! Requested (%s), got %s:\n%s"
                % (command, allowed, response_code, decoded)
            )
            raise RainbirdApiException("Unexpected response from Rain Bird device")
        return funct(decoded)

    async def _cacheable_command(
        self, funct: Callable[[dict[str, Any]], T], command: str, *args
    ) -> T:
        key = f"{command}-{args}"
        if result := self._cache.get(key):
            _LOGGER.debug("Returned cached result for key '%s'", key)
            return result
        result = await self._process_command(funct, command, *args)
        self._cache[key] = result
        return result  # type: ignore
