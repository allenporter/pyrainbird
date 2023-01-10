"""Client library for rainbird.

This is an asyncio based client library for rainbird.
"""

import datetime
import logging
from collections.abc import Callable
from http import HTTPStatus
from typing import Any, Optional, TypeVar

import aiohttp
from aiohttp.client_exceptions import ClientError, ClientResponseError

from . import encryption, rainbird
from .data import (
    _DEFAULT_PAGE,
    AvailableStations,
    ControllerFirmwareVersion,
    ControllerState,
    ModelAndVersion,
    NetworkStatus,
    ProgramInfo,
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
from .exceptions import RainbirdApiException, RainbirdAuthException
from .resources import LENGTH, RAINBIRD_COMMANDS, RAINBIRD_RESPONSES, RESPONSE

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

CLOUD_API_URL = "http://rdz-rbcloud.rainbird.com/phone-api"


class AsyncRainbirdClient:
    """An asyncio rainbird client."""

    def __init__(
        self,
        websession: aiohttp.ClientSession,
        host: str,
        password: Optional[str],
    ) -> None:
        self._websession = websession
        if host.startswith("/") or host.startswith("http://"):
            self._url = host
        else:
            self._url = f"http://{host}/stick"
        self._coder = encryption.PayloadCoder(password, _LOGGER)

    async def tunnelSip(self, data: str, length: int) -> str:
        """Send a tunnelSip request."""
        result = await self.request("tunnelSip", {"data": data, LENGTH: length})
        return result["data"]

    async def request(
        self, method: str, params: dict[str, Any] = None
    ) -> dict[str, Any]:
        """Send a request for any command."""
        payload = self._coder.encode_command(method, params or {})
        try:
            resp = await self._websession.request(
                "post", self._url, data=payload, headers=HEAD
            )
            resp.raise_for_status()
        except ClientResponseError as err:
            if err.status == HTTPStatus.FORBIDDEN:
                raise RainbirdAuthException(
                    f"Error authenticating with Device: {err}"
                ) from err
            raise RainbirdApiException(f"Error from API: {str(err)}") from err
        except ClientError as err:
            raise RainbirdApiException(
                f"Error communicating with device: {str(err)}"
            ) from err
        content = await resp.read()
        return self._coder.decode_command(content)


def CreateController(
    websession: aiohttp.ClientSession, host: str, password: str
) -> "AsyncRainbirdController":
    local_client = AsyncRainbirdClient(websession, host, password)
    cloud_client = AsyncRainbirdClient(websession, CLOUD_API_URL, None)
    return AsyncRainbirdController(local_client, cloud_client)


class AsyncRainbirdController:
    """Rainbord controller that uses asyncio."""

    def __init__(
        self,
        local_client: AsyncRainbirdClient,
        cloud_client: AsyncRainbirdClient = None,
    ) -> None:
        """Initialize AsyncRainbirdController."""
        self._local_client = local_client
        self._cloud_client = cloud_client

    async def get_model_and_version(self) -> ModelAndVersion:
        """Return the model and version."""
        return await self._process_command(
            lambda response: ModelAndVersion(
                response["modelID"],
                response["protocolRevisionMajor"],
                response["protocolRevisionMinor"],
            ),
            "ModelAndVersionRequest",
        )

    async def get_available_stations(self, page=_DEFAULT_PAGE) -> AvailableStations:
        """Get the available stations."""
        mask = (
            "%%0%dX"
            % RAINBIRD_RESPONSES["AvailableStationsResponse"]["setStations"][LENGTH]
        )
        return await self._process_command(
            lambda resp: AvailableStations(
                mask % resp["setStations"], page=resp["pageNumber"]
            ),
            "AvailableStationsRequest",
            page,
        )

    async def get_serial_number(self) -> str:
        """Get the device serial number."""
        return await self._process_command(
            lambda resp: resp["serialNumber"], "SerialNumberRequest"
        )

    async def get_current_time(self) -> datetime.time:
        """Get the device current time."""
        return await self._process_command(
            lambda resp: datetime.time(resp["hour"], resp["minute"], resp["second"]),
            "CurrentTimeRequest",
        )

    async def get_current_date(self) -> datetime.date:
        """Get the device current date."""
        return await self._process_command(
            lambda resp: datetime.date(resp["year"], resp["month"], resp["day"]),
            "CurrentDateRequest",
        )

    async def get_wifi_params(self) -> WifiParams:
        """Return wifi parameters and other settings."""
        result = await self._local_client.request("getWifiParams")
        return WifiParams.parse_obj(result)

    async def get_settings(self) -> Settings:
        """Return a combined set of device settings."""
        result = await self._local_client.request("getSettings")
        return Settings.parse_obj(result)

    async def get_weather_adjustment_mask(self) -> WeatherAdjustmentMask:
        """Return the weather adjustment mask, subset of the settings."""
        result = await self._local_client.request("getWeatherAdjustmentMask")
        return WeatherAdjustmentMask.parse_obj(result)

    async def get_zip_code(self) -> ZipCode:
        """Return zip code and location, a subset of the settings."""
        result = await self._local_client.request("getZipCode")
        return ZipCode.parse_obj(result)

    async def get_program_info(self) -> ProgramInfo:
        """Return program information, a subset of the settings."""
        result = await self._local_client.request("getProgramInfo")
        return ProgramInfo.parse_obj(result)

    async def get_network_status(self) -> NetworkStatus:
        """Return the device network status."""
        result = await self._local_client.request("getNetworkStatus")
        return NetworkStatus.parse_obj(result)

    async def get_server_mode(self) -> ServerMode:
        """Return details about the device server setup."""
        result = await self._local_client.request("getServerMode")
        return ServerMode.parse_obj(result)

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

    async def get_zone_states(self, page=_DEFAULT_PAGE) -> States:
        """Return the current state of the zone."""
        mask = (
            "%%0%dX"
            % RAINBIRD_RESPONSES["CurrentStationsActiveResponse"]["activeStations"][
                LENGTH
            ]
        )
        return await self._process_command(
            lambda resp: States((mask % resp["activeStations"])[:4]),
            "CurrentStationsActiveRequest",
            page,
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
        """Advance to the zone with the specified param."""
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
        return ScheduleAndSettings.parse_obj(result)

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
        return WeatherAndStatus.parse_obj(result)

    async def get_combined_controller_state(self) -> ControllerState:
        """Return the combined controller state."""
        return await self._process_command(
            lambda resp: ControllerState.parse_obj(resp),
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

    async def get_schedule(self, command_code: str) -> dict[str, Any]:
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
        """Debugging command to see if the device supports the specified json RPC method."""
        return await self._local_client.request(rpc)

    async def _command(self, command: str, *args) -> dict[str, Any]:
        data = rainbird.encode(command, *args)
        _LOGGER.debug("Request to line: " + str(data))
        command_data = RAINBIRD_COMMANDS[command]
        decrypted_data = await self._local_client.tunnelSip(
            data,
            command_data[LENGTH],
        )
        _LOGGER.debug("Response from line: " + str(decrypted_data))
        decoded = rainbird.decode(decrypted_data)
        response_code = decrypted_data[:2]
        expected_response_code = command_data[RESPONSE]
        if response_code != expected_response_code:
            raise RainbirdApiException(
                "Status request failed with wrong response! Requested %s but got %s:\n%s"
                % (expected_response_code, response_code, decoded)
            )
        _LOGGER.debug("Response: %s" % decoded)
        return decoded

    async def _process_command(
        self, funct: Callable[[dict[str, Any]], T], command: str, *args
    ) -> T:
        response = await self._command(command, *args)
        return funct(response)
