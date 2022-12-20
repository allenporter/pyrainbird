"""Test for AsyncRainbirdController."""

import datetime
from collections.abc import Awaitable, Callable

import aiohttp
import pytest

from pyrainbird import (
    RAINBIRD_COMMANDS,
    AvailableStations,
    ModelAndVersion,
    WaterBudget,
)
from pyrainbird.async_client import (
    AsyncRainbirdClient,
    AsyncRainbirdController,
    RainbirdApiException,
)
from pyrainbird.encryption import encrypt

from .conftest import LENGTH, PASSWORD, REQUEST, RESPONSE, RESULT_DATA, ResponseResult


async def test_request(
    rainbird_client: Callable[[], Awaitable[AsyncRainbirdClient]],
    response: ResponseResult,
) -> None:
    """Test of basic request/response handling."""
    response(aiohttp.web.Response(body=RESPONSE))
    client = await rainbird_client()
    resp = await client.request(REQUEST, LENGTH)
    assert resp == RESULT_DATA


async def test_request_failure(
    rainbird_client: Callable[[], Awaitable[AsyncRainbirdClient]],
    response: ResponseResult,
) -> None:
    """Test a basic request failure handling."""

    response(aiohttp.web.Response(status=500))
    client = await rainbird_client()
    with pytest.raises(RainbirdApiException):
        await client.request(REQUEST, LENGTH)


@pytest.fixture(name="api_response")
def mock_api_response(response: ResponseResult) -> Callable[[...], Awaitable[None]]:
    """Fixture to construct a fake API response."""

    def _put_result(command: str, **kvargs) -> None:
        resp = RAINBIRD_COMMANDS["ControllerResponses"][command]
        data = command + ("00" * (resp["length"] - 1))
        for k in resp:
            if k in ["type", "length"]:
                continue
            param_template = "%%0%dX" % (resp[k]["length"])
            start_ = resp[k]["position"]
            end_ = start_ + resp[k]["length"]
            data = "%s%s%s" % (
                data[:start_],
                (param_template % kvargs[k]),
                data[end_:],
            )

        body = encrypt(
            ('{"jsonrpc": "2.0", "result": {"data":"%s"}, "id": 1} ' % data),
            PASSWORD,
        )
        response(aiohttp.web.Response(body=body))

    return _put_result


async def test_get_model_and_version(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    api_response("82", modelID=16, protocolRevisionMajor=1, protocolRevisionMinor=3)
    assert await controller.get_model_and_version() == ModelAndVersion(16, 1, 3)


async def test_get_available_stations(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    api_response("83", pageNumber=1, setStations=0x7F000000)
    assert await controller.get_available_stations() == AvailableStations("7f000000", 1)


async def test_get_serial_number(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    api_response("85", serialNumber=0x12635436566)
    assert await controller.get_serial_number() == 0x12635436566


async def test_get_current_time(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    time = datetime.time()
    api_response("90", hour=time.hour, minute=time.minute, second=time.second)
    assert await controller.get_current_time() == time


async def test_get_current_date(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    date = datetime.date.today()
    api_response("92", year=date.year, month=date.month, day=date.day)
    assert await controller.get_current_date() == date


async def test_get_water_budget(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    api_response("B0", programCode=1, seasonalAdjust=65)
    assert await controller.water_budget(5) == WaterBudget(1, 65)


@pytest.mark.parametrize(
    "state,expected",
    [(1, True), (0, False)],
)
async def test_get_rain_sensor(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
    state: int,
    expected: bool,
) -> None:
    controller = await rainbird_controller()
    api_response("BE", sensorState=state)
    assert await controller.get_rain_sensor_state() == expected


async def test_get_zone_state(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    for i in range(1, 9):
        for j in range(1, 9):
            mask = (1 << (i - 1)) * 0x1000000
            api_response("BF", pageNumber=0, activeStations=mask)
            assert await controller.get_zone_state(j) == (i == j)


async def test_set_program(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    api_response("01", commandEcho=5)
    await controller.set_program(5)


async def test_irrigate_zone(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    api_response("01", pageNumber=0, commandEcho=6)
    api_response("BF", pageNumber=0, activeStations=0b10000000000000000000000000000)
    await controller.irrigate_zone(5, 30)


async def test_test_zone(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    api_response("01", commandEcho=6)
    await controller.test_zone(6)


async def test_stop_irrigation(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    api_response("01", pageNumber=0, commandEcho=6)
    api_response("BF", pageNumber=0, activeStations=0b0)
    await controller.stop_irrigation()


async def test_get_rain_delay(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    api_response("B6", delaySetting=16)
    await controller.get_rain_delay() == 16


async def test_set_rain_delay(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    api_response("01", pageNumber=0, commandEcho=6)
    await controller.set_rain_delay(3)


async def test_advance_zone(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    api_response("01", commandEcho=3)
    await controller.advance_zone(3)


@pytest.mark.parametrize(
    "state,expected",
    [
        (1, True),
        (0, False),
    ],
)
async def test_get_current_irrigation(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
    state: int,
    expected: bool,
) -> None:
    controller = await rainbird_controller()
    api_response("C8", irrigationState=state)
    assert await controller.get_current_irrigation() == expected


async def test_not_acknowledge_response(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    api_response("00", commandEcho=17, NAKCode=28)
    with pytest.raises(RainbirdApiException):
        await controller.irrigate_zone(1, 30)
