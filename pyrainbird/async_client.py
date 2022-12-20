"""Client library for rainbird.

This is an asyncio based client library for rainbird.
"""

import datetime
import logging
from collections.abc import Callable
from typing import Any, TypeVar

import aiohttp
from aiohttp.client_exceptions import ClientError

from . import encryption, rainbird
from .data import _DEFAULT_PAGE, AvailableStations, ModelAndVersion, States, WaterBudget
from .resources import RAINBIRD_COMMANDS

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


class RainbirdApiException(Exception):
    """Exception from rainbird api."""


class AsyncRainbirdClient:
    """An asyncio rainbird client."""

    def __init__(
        self, websession: aiohttp.ClientSession, host: str, password: str
    ) -> None:
        self._websession = websession
        self._url = host if host.startswith("/") else f"http://{host}/stick"
        self._coder = encryption.PayloadCoder(password, _LOGGER)

    async def request(self, data: str, length: int) -> str:
        payload = self._coder.encode_request(data, length)
        try:
            resp = await self._websession.request("post", self._url, data=payload, headers=HEAD)
            resp.raise_for_status()
        except ClientError as err:
            raise RainbirdApiException(f"Error from API: {str(err)}") from err
        content = await resp.read()
        return self._coder.decode_response(content)


class AsyncRainbirdController:
    """Rainbord controller that uses asyncio."""

    def __init__(self, client: AsyncRainbirdClient):
        """Initialize AsyncRainbirdController."""
        self._client = client

    async def get_model_and_version(self) -> ModelAndVersion:
        """Return the model and version."""
        return await self._process_command(
            lambda response: ModelAndVersion(
                response["modelID"],
                response["protocolRevisionMajor"],
                response["protocolRevisionMinor"],
            ),
            "ModelAndVersion",
        )

    async def get_available_stations(self, page=_DEFAULT_PAGE) -> AvailableStations:
        """Get the available stations."""
        mask = (
            "%%0%dX"
            % RAINBIRD_COMMANDS["ControllerResponses"]["83"]["setStations"]["length"]
        )
        return await self._process_command(
            lambda resp: AvailableStations(
                mask % resp["setStations"], page=resp["pageNumber"]
            ),
            "AvailableStations",
            page,
        )

    async def get_serial_number(self) -> str:
        """Get the device serial number."""
        return await self._process_command(
            lambda resp: resp["serialNumber"], "SerialNumber"
        )

    async def get_current_time(self) -> datetime.time:
        """Get the device current time."""
        return await self._process_command(
            lambda resp: datetime.time(resp["hour"], resp["minute"], resp["second"]),
            "CurrentTime",
        )

    async def get_current_date(self) -> datetime.date:
        """Get the device current date."""
        return await self._process_command(
            lambda resp: datetime.date(resp["year"], resp["month"], resp["day"]),
            "CurrentDate",
        )

    async def water_budget(self, budget) -> WaterBudget:
        """Return the water budget."""
        return await self._process_command(
            lambda resp: WaterBudget(resp["programCode"], resp["seasonalAdjust"]),
            "WaterBudget",
            budget,
        )

    async def get_rain_sensor_state(self) -> bool:
        """Get the current state for the rain sensor."""
        return await self._process_command(
            lambda resp: bool(resp["sensorState"]),
            "CurrentRainSensorState",
        )

    async def get_zone_states(self, page=_DEFAULT_PAGE) -> States:
        """Return the current state of the zone."""
        mask = (
            "%%0%dX"
            % RAINBIRD_COMMANDS["ControllerResponses"]["BF"]["activeStations"]["length"]
        )
        return await self._process_command(
            lambda resp: States((mask % resp["activeStations"])[:4]),
            "CurrentStationsActive",
            page,
        )

    async def get_zone_state(self, zone: int) -> bool:
        """Return the current state of the zone."""
        states = await self.get_zone_states()
        return states.active(zone)

    async def set_program(self, program: int) -> None:
        """Start a program."""
        await self._process_command(lambda resp: True, "ManuallyRunProgram", program)

    async def test_zone(self, zone: int) -> None:
        """Test a zone."""
        await self._process_command(lambda resp: True, "TestStations", zone)

    async def irrigate_zone(self, zone: int, minutes: int) -> None:
        """Send the irrigate command."""
        await self._process_command(
            lambda resp: True, "ManuallyRunStation", zone, minutes
        )

    async def stop_irrigation(self) -> None:
        """Send the stop command."""
        await self._process_command(lambda resp: True, "StopIrrigation")

    async def get_rain_delay(self) -> int:
        """Return the current rain delay value."""
        return await self._process_command(
            lambda resp: resp["delaySetting"], "RainDelayGet"
        )

    async def set_rain_delay(self, days: int) -> None:
        """Set the rain delay value in days."""
        await self._process_command(lambda resp: True, "RainDelaySet", days)

    async def advance_zone(self, param: int) -> None:
        """Advance to the zone with the specified param."""
        await self._process_command(lambda resp: True, "AdvanceStation", param)

    async def get_current_irrigation(self) -> bool:
        """Return True if the irrigation state is on."""
        return await self._process_command(
            lambda resp: bool(resp["irrigationState"]),
            "CurrentIrrigationState",
        )

    async def _command(self, command: str, *args) -> dict[str, Any]:
        data = rainbird.encode(command, *args)
        _LOGGER.debug("Request to line: " + str(data))
        decrypted_data = await self._client.request(
            data,
            RAINBIRD_COMMANDS["ControllerCommands"]["%sRequest" % command]["length"],
        )
        _LOGGER.debug("Response from line: " + str(decrypted_data))
        decoded = rainbird.decode(decrypted_data)
        if (
            decrypted_data[:2]
            != RAINBIRD_COMMANDS["ControllerCommands"]["%sRequest" % command][
                "response"
            ]
        ):
            raise RainbirdApiException(
                "Status request failed with wrong response! Requested %s but got %s:\n%s"
                % (
                    RAINBIRD_COMMANDS["ControllerCommands"]["%sRequest" % command][
                        "response"
                    ],
                    decrypted_data[:2],
                    decoded,
                )
            )
        _LOGGER.debug("Response: %s" % decoded)
        return decoded

    async def _process_command(
        self, funct: Callable[[dict[str, Any]], T], cmd, *args
    ) -> T:
        response = await self._command(cmd, *args)
        response_type = response["type"]
        expected_type = RAINBIRD_COMMANDS["ControllerResponses"][
            RAINBIRD_COMMANDS["ControllerCommands"][cmd + "Request"]["response"]
        ]["type"]
        if response_type != expected_type:
            raise RainbirdApiException(
                f"Response type '{response_type}' did not match '{expected_type}"
            )
        return funct(response)
