"""Test for AsyncRainbirdController."""

import datetime
import json
from collections.abc import Awaitable, Callable

import aiohttp
import pytest

from pyrainbird import (
    AvailableStations,
    ModelAndVersion,
    WaterBudget,
)
from pyrainbird.async_client import AsyncRainbirdClient, AsyncRainbirdController
from pyrainbird.data import SoilType
from pyrainbird.encryption import encrypt
from pyrainbird.exceptions import RainbirdApiException, RainbirdAuthException
from pyrainbird.resources import RAINBIRD_RESPONSES_BY_ID, RESERVED_FIELDS

from .conftest import LENGTH, PASSWORD, REQUEST, RESPONSE, RESULT_DATA, ResponseResult


async def test_request(
    rainbird_client: Callable[[], Awaitable[AsyncRainbirdClient]],
    response: ResponseResult,
) -> None:
    """Test of basic request/response handling."""
    response(aiohttp.web.Response(body=RESPONSE))
    client = await rainbird_client()
    resp = await client.tunnelSip(REQUEST, LENGTH)
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


async def test_request_permission_failure(
    rainbird_client: Callable[[], Awaitable[AsyncRainbirdClient]],
    response: ResponseResult,
) -> None:
    """Test a basic request failure handling."""

    response(aiohttp.web.Response(status=403))
    client = await rainbird_client()
    with pytest.raises(RainbirdAuthException):
        await client.request(REQUEST, LENGTH)


@pytest.fixture(name="api_response")
def mock_api_response(response: ResponseResult) -> Callable[[...], Awaitable[None]]:
    """Fixture to construct a fake API response."""

    def _put_result(command: str, **kvargs) -> None:
        resp = RAINBIRD_RESPONSES_BY_ID[command]
        data = command + ("00" * (resp["length"] - 1))
        for k in resp:
            if k in RESERVED_FIELDS:
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


async def test_get_network_status(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    response: ResponseResult,
) -> None:
    controller = await rainbird_controller()
    payload = json.dumps(
        {"jsonrpc": "2.0", "result": {"networkUp": True, "internetUp": True}, "id": 0}
    )
    response(aiohttp.web.Response(body=encrypt(payload, PASSWORD)))
    result = await controller.get_network_status()
    assert result
    assert result.network_up
    assert result.internet_up


async def test_get_wifi_params(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    response: ResponseResult,
) -> None:
    controller = await rainbird_controller()
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "result": {
                "macAddress": "11:22:33:44:55:66",
                "localIpAddress": "192.168.1.10",
                "localNetmask": "255.255.255.0",
                "localGateway": "192.168.1.1",
                "rssi": -59,
                "wifiSsid": "some-ssid",
                "wifiPassword": "some-pass",
                "wifiSecurity": "wpa2-aes",
                "apTimeoutNoLan": 20,
                "apTimeoutIdle": 20,
                "apSecurity": "unknown",
                "stickVersion": "Rain Bird Stick Rev C/1.63",
            },
            "id": 1234,
        }
    )
    response(aiohttp.web.Response(body=encrypt(payload, PASSWORD)))
    params = await controller.get_wifi_params()
    assert params.dict() == {
        "ap_security": "unknown",
        "ap_timeout_idle": 20,
        "ap_timeout_no_lan": 20,
        "local_gateway": "192.168.1.1",
        "local_ip_address": "192.168.1.10",
        "local_netmask": "255.255.255.0",
        "mac_address": "11:22:33:44:55:66",
        "rssi": -59,
        "sick_version": "Rain Bird Stick Rev C/1.63",
        "wifi_password": "some-pass",
        "wifi_security": "wpa2-aes",
        "wifi_ssid": "some-ssid",
    }


async def test_get_schedule_and_settings(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    response: ResponseResult,
) -> None:
    controller = await rainbird_controller()
    payload = {
        "id": 440,
        "jsonrpc": "2.0",
        "result": {
            "0300": "83003F000000",
            "0B": "8B012F0000",
            "3000": "B0000064",
            "3001": "B0010050",
            "3002": "B0020050",
            "3B00": "BB0000000000000000FF0000",
            "3F00": "BF0000000000",
            "4A01": "CA012B483163",
            "4C": "CC1228270417E700040001FFFF000000",
            "schedule": {
                "200000": "A0000000000400",
                "200010": "A000106A0601006401",
                "200011": "A000116A0300006400",
                "200012": "A00012000300006400",
                "200060": "A0006000F0FFFFFFFFFFFF",
                "200061": "A00061FFFFFFFFFFFFFFFF",
                "200062": "A00062FFFFFFFFFFFFFFFF",
                "200080": "A00080001900000000001400000000",
                "200081": "A00081000700000000001400000000",
                "200082": "A00082000A00000000000000000000",
                "200083": "A00083000000000000000000000000",
                "200084": "A00084000000000000000000000000",
                "200085": "A00085000000000000000000000000",
                "3000": "B0000064",
                "3001": "B0010050",
                "3002": "B0020050",
                "3100": "0131",
                "3101": "0131",
                "3102": "0131",
                "31FF0064": "0131",
            },
            "settings": {
                "FlowRates": [],
                "FlowUnits": [],
                "code": "90210",
                "country": "US",
                "globalDisable": False,
                "numPrograms": 2,
                "programOptOutMask": "07",
                "soilTypes": [1, 0, 0],
            },
            "status": "good",
        },
    }
    response(aiohttp.web.json_response(payload))
    result = await controller.get_schedule_and_settings("11:22:33:44:55:66")
    assert result.settings
    settings = result.settings
    assert settings.flow_rates == []
    assert settings.flow_units == []
    assert settings.code == "90210"
    assert settings.country == "US"
    assert not settings.global_disable
    assert settings.num_programs == 2
    assert settings.program_opt_out_mask == "07"
    assert settings.soil_types == [SoilType.CLAY, 0, 0]
    assert result.status == "good"


async def test_get_server_mode(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    response: ResponseResult,
) -> None:
    """Test the get server mode rpc."""
    controller = await rainbird_controller()
    payload = {
        "jsonrpc": "2.0",
        "result": {
            "serverMode": True,
            "checkInInterval": 10,
            "serverUrl": "http://rdz-rbcloud.rainbird.com:80/rdz-api",
            "relayTimeout": 5,
            "missedCheckins": 0,
        },
        "id": 0,
    }
    response(aiohttp.web.Response(body=encrypt(json.dumps(payload), PASSWORD)))
    result = await controller.get_server_mode()
    assert result.server_mode
    assert result.check_in_interval == 10
    assert result.server_url == "http://rdz-rbcloud.rainbird.com:80/rdz-api"
    assert result.relay_timeout == 5
    assert result.missed_checkins == 0


async def test_get_settings(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    response: ResponseResult,
) -> None:
    """Test getting the settings."""
    controller = await rainbird_controller()
    payload = {
        "jsonrpc": "2.0",
        "result": {
            "country": "US",
            "code": "90210",
            "globalDisable": True,
            "numPrograms": 3,
            "programOptOutMask": "07",
            "SoilTypes": [1, 0, 0],
            "FlowRates": [0, 0, 0],
            "FlowUnits": [0, 0, 0],
        },
        "id": 0,
    }
    response(aiohttp.web.Response(body=encrypt(json.dumps(payload), PASSWORD)))
    result = await controller.get_settings()
    assert result.global_disable
    assert result.num_programs == 3
    assert result.program_opt_out_mask == "07"
    assert result.soil_types == [SoilType.CLAY, SoilType.NONE, SoilType.NONE]
    assert result.flow_rates == [0, 0, 0]
    assert result.flow_units == [0, 0, 0]
    assert result.country == "US"
    assert result.code == "90210"


async def test_get_zip_code(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    response: ResponseResult,
) -> None:
    """Test the get zip code rpc."""
    controller = await rainbird_controller()
    payload = {"jsonrpc": "2.0", "result": {"country": "US", "code": "90210"}, "id": 0}
    response(aiohttp.web.Response(body=encrypt(json.dumps(payload), PASSWORD)))
    result = await controller.get_zip_code()
    assert result.country == "US"
    assert result.code == "90210"


async def test_get_weather_adjustment_mask(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    response: ResponseResult,
) -> None:
    """Test getting the weather adjustment mask."""
    controller = await rainbird_controller()
    payload = {
        "jsonrpc": "2.0",
        "result": {"globalDisable": True, "numPrograms": 3, "programOptOutMask": "07"},
        "id": 0,
    }
    response(aiohttp.web.Response(body=encrypt(json.dumps(payload), PASSWORD)))
    result = await controller.get_weather_adjustment_mask()
    assert result.global_disable
    assert result.num_programs == 3
    assert result.program_opt_out_mask == "07"


async def test_get_combined_controller_state(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    response: ResponseResult,
) -> None:
    """Test getting the combined controller state."""
    controller = await rainbird_controller()
    payload = {
        "jsonrpc": "2.0",
        "result": {"data": "CC140B230817E700030001FFFF000000"},
        "id": 0,
    }
    response(aiohttp.web.Response(body=encrypt(json.dumps(payload), PASSWORD)))
    result = await controller.get_combined_controller_state()
    assert result
    assert result.delay_setting == 3
    assert result.sensor_state == 0
    assert result.irrigation_state == 1
    assert result.seasonal_adjust == 65535
    assert result.remaining_runtime == 0
    assert result.active_station == 0
    assert result.device_time == datetime.datetime(2023, 1, 8, 20, 11, 35)
