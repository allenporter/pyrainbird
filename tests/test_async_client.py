"""Test for AsyncRainbirdController."""

from __future__ import annotations

import datetime
import json
from collections.abc import Awaitable, Callable

import aiohttp
import pytest
from freezegun import freeze_time

from pyrainbird import rainbird
from pyrainbird.async_client import AsyncRainbirdClient, AsyncRainbirdController
from pyrainbird.data import (
    DayOfWeek,
    ModelAndVersion,
    ProgramFrequency,
    SoilType,
    WaterBudget,
)
from pyrainbird.encryption import encrypt
from pyrainbird.exceptions import (
    RainbirdApiException,
    RainbirdAuthException,
    RainbirdDeviceBusyException,
)
from pyrainbird.resources import RAINBIRD_COMMANDS_BY_ID

from .conftest import LENGTH, PASSWORD, REQUEST, RESPONSE, RESULT_DATA, ResponseResult


async def test_request(
    rainbird_client: Callable[[], Awaitable[AsyncRainbirdClient]],
    response: ResponseResult,
) -> None:
    """Test of basic request/response handling."""
    response(aiohttp.web.Response(body=RESPONSE))
    client = await rainbird_client()
    resp = await client.request("method", {"key": "value"})
    assert resp == {"data": RESULT_DATA}


async def test_request_failure(
    rainbird_client: Callable[[], Awaitable[AsyncRainbirdClient]],
    response: ResponseResult,
) -> None:
    """Test a basic request failure handling."""

    response(aiohttp.web.Response(status=500))
    client = await rainbird_client()
    with pytest.raises(RainbirdApiException):
        await client.request(REQUEST, LENGTH)


async def test_device_busy_failure(
    rainbird_client: Callable[[], Awaitable[AsyncRainbirdClient]],
    response: ResponseResult,
) -> None:
    """Test a basic request failure handling."""

    response(aiohttp.web.Response(status=503))
    client = await rainbird_client()
    with pytest.raises(RainbirdDeviceBusyException):
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


@pytest.fixture(name="encrypt_response")
def mock_encrypt_response(response: ResponseResult) -> Callable[[...], None]:
    """Fixture to encrypt API responses."""

    def _put_result(plaintext: str | dict) -> None:
        if isinstance(plaintext, dict):
            plaintext = json.dumps(plaintext)
        body = encrypt(plaintext, PASSWORD)
        response(aiohttp.web.Response(body=body))

    return _put_result


@pytest.fixture(name="api_response")
def mock_api_response(
    encrypt_response: Callable[[str | dict], None],
) -> Callable[[...], None]:
    """Fixture to construct a fake API response."""

    def _put_result(command: str, **kvargs) -> None:
        command_set = RAINBIRD_COMMANDS_BY_ID[command]
        data = rainbird.encode_command(command_set, *kvargs.values())
        encrypt_response({"jsonrpc": "2.0", "result": {"data": data}, "id": 1})

    return _put_result


@pytest.fixture(name="sip_data_responses")
def mock_sip_data_responses(
    encrypt_response: Callable[[str | dict], None],
) -> Callable[[list[str]], None]:
    """Fixture to create sip data responess."""

    def _put_result(datam: list[str]) -> None:
        for data in datam:
            encrypt_response({"jsonrpc": "2.0", "result": {"data": data}, "id": 1})

    return _put_result


async def test_get_model_and_version(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    api_response("82", modelID=0x0A, protocolRevisionMajor=1, protocolRevisionMinor=3)
    result = await controller.get_model_and_version()
    assert result == ModelAndVersion(0x0A, 1, 3)
    assert result.model_code == "ESP_TM2v2"
    assert result.model_name == "ESP-TM2"
    model_info = result.model_info
    assert model_info.code == "ESP_TM2v2"
    assert model_info.name == "ESP-TM2"
    assert model_info.supports_water_budget
    assert model_info.max_programs == 3
    assert model_info.max_run_times == 4


async def test_get_available_stations(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    api_response("83", pageNumber=1, setStations=0x7F000000)
    stations = await controller.get_available_stations()
    assert stations.active_set == {1, 2, 3, 4, 5, 6, 7}


async def test_get_serial_number(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    api_response("85", serialNumber=0x12635436566)
    assert await controller.get_serial_number() == 0x12635436566
    # Result is cached
    assert await controller.get_serial_number() == 0x12635436566
    assert await controller.get_serial_number() == 0x12635436566
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
    api_response("92", day=date.day, month=date.month, year=date.year)
    assert await controller.get_current_date() == date


async def test_set_current_time(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    """Test for setting the current time."""
    controller = await rainbird_controller()
    api_response("01", commandEcho="11")
    await controller.set_current_time(datetime.datetime.now().time())


async def test_set_current_date(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    """Test for setting the current date."""
    controller = await rainbird_controller()
    api_response("01", commandEcho="13")
    await controller.set_current_date(datetime.date.today())


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


async def test_get_zone_states(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    for i in range(1, 8):
        mask = (1 << (i - 1)) * 0x1000000
        api_response("BF", pageNumber=0, activeStations=mask)
        states = await controller.get_zone_states()
        assert i in states.active_set
        assert i - 1 not in states.active_set
        assert i + 1 not in states.active_set


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
    encrypt_response: ResponseResult,
) -> None:
    controller = await rainbird_controller()
    payload = {
        "jsonrpc": "2.0",
        "result": {"networkUp": True, "internetUp": True},
        "id": 0,
    }
    encrypt_response(payload)
    result = await controller.get_network_status()
    assert result
    assert result.network_up
    assert result.internet_up


async def test_get_wifi_params(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    encrypt_response: ResponseResult,
) -> None:
    controller = await rainbird_controller()
    payload = {
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
    encrypt_response(payload)
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
    encrypt_response: ResponseResult,
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
    encrypt_response(payload)
    result = await controller.get_server_mode()
    assert result.server_mode
    assert result.check_in_interval == 10
    assert result.server_url == "http://rdz-rbcloud.rainbird.com:80/rdz-api"
    assert result.relay_timeout == 5
    assert result.missed_checkins == 0


async def test_get_settings(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    encrypt_response: ResponseResult,
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
    encrypt_response(payload)
    result = await controller.get_settings()
    assert result.global_disable
    assert result.num_programs == 3
    assert result.program_opt_out_mask == "07"
    assert result.soil_types == [SoilType.CLAY, SoilType.NONE, SoilType.NONE]
    assert result.flow_rates == [0, 0, 0]
    assert result.flow_units == [0, 0, 0]
    assert result.country == "US"
    assert result.code == "90210"


async def test_get_program_info(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    encrypt_response: ResponseResult,
) -> None:
    """Test getting the settings."""
    controller = await rainbird_controller()
    payload = {
        "jsonrpc": "2.0",
        "result": {
            "SoilTypes": [1, 0, 0],
            "FlowRates": [0, 0, 0],
            "FlowUnits": [0, 0, 0],
        },
        "id": 0,
    }
    encrypt_response(payload)
    result = await controller.get_program_info()
    assert result
    assert result.soil_types == [SoilType.CLAY, SoilType.NONE, SoilType.NONE]
    assert result.flow_rates == [0, 0, 0]
    assert result.flow_units == [0, 0, 0]


async def test_get_zip_code(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    encrypt_response: ResponseResult,
) -> None:
    """Test the get zip code rpc."""
    controller = await rainbird_controller()
    payload = {"jsonrpc": "2.0", "result": {"country": "US", "code": "90210"}, "id": 0}
    encrypt_response(payload)
    result = await controller.get_zip_code()
    assert result.country == "US"
    assert result.code == "90210"


async def test_get_weather_adjustment_mask(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    encrypt_response: ResponseResult,
) -> None:
    """Test getting the weather adjustment mask."""
    controller = await rainbird_controller()
    payload = {
        "jsonrpc": "2.0",
        "result": {
            "globalDisable": True,
            "numPrograms": 3,
            "programOptOutMask": "07",
        },
        "id": 0,
    }
    encrypt_response(payload)
    result = await controller.get_weather_adjustment_mask()
    assert result.global_disable
    assert result.num_programs == 3
    assert result.program_opt_out_mask == "07"


async def test_get_combined_controller_state(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    encrypt_response: ResponseResult,
) -> None:
    """Test getting the combined controller state."""
    controller = await rainbird_controller()
    payload = {
        "jsonrpc": "2.0",
        "result": {"data": "CC140B230817E700030001FFFF000000"},
        "id": 0,
    }
    encrypt_response(payload)
    result = await controller.get_combined_controller_state()
    assert result
    assert result.delay_setting == 3
    assert result.sensor_state == 0
    assert result.irrigation_state == 1
    assert result.seasonal_adjust == 65535
    assert result.remaining_runtime == 0
    assert result.active_station == 0
    assert result.device_time == datetime.datetime(2023, 1, 8, 20, 11, 35)


async def test_get_controller_firmware_version(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    encrypt_response: ResponseResult,
) -> None:
    """Test getting the controller firmware version."""
    controller = await rainbird_controller()
    payload = {
        "jsonrpc": "2.0",
        "result": {"length": 5, "data": "8B012F0000"},
        "id": 0,
    }
    encrypt_response(payload)
    result = await controller.get_controller_firmware_version()
    assert result
    assert result.major == 1
    assert result.minor == 47
    assert result.patch == 0


async def test_get_command_support(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    encrypt_response: ResponseResult,
) -> None:
    """Test the command for testing if a command is supported."""
    controller = await rainbird_controller()
    payload = {
        "jsonrpc": "2.0",
        "result": {"length": 3, "data": "840701"},
        "id": 0,
    }
    encrypt_response(payload)
    assert await controller.test_command_support("07")


async def test_rpc_command_support(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    encrypt_response: ResponseResult,
) -> None:
    """Test checking for an RPC support."""
    controller = await rainbird_controller()
    payload = {
        "jsonrpc": "2.0",
        "result": {"apSecurity": "unknown"},
        "id": 0,
    }
    encrypt_response(payload)
    result = await controller.test_rpc_support("getWifiParams")
    assert result == {"apSecurity": "unknown"}


async def test_error_response(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    encrypt_response: ResponseResult,
) -> None:
    """Test checking for an RPC support."""
    controller = await rainbird_controller()
    payload = {
        "jsonrpc": "2.0",
        "error": {"code": -32601, "message": "Method not found"},
        "id": "null",
    }
    encrypt_response(payload)
    with pytest.raises(RainbirdApiException, match=r"Method not found"):
        await controller.test_rpc_support("invalid")


async def test_unknown_error_response(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    encrypt_response: ResponseResult,
) -> None:
    """Test checking for an RPC support."""
    controller = await rainbird_controller()
    payload = {
        "jsonrpc": "2.0",
        "error": {"code": 9090, "message": "Some error"},
        "id": "null",
    }
    encrypt_response(payload)
    with pytest.raises(RainbirdApiException, match=r"Some error"):
        await controller.test_rpc_support("invalid")


async def test_unrecognized_response(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    encrypt_response: ResponseResult,
) -> None:
    """Test checking for an RPC support."""
    controller = await rainbird_controller()
    payload = {
        "jsonrpc": "2.0",
        "result": {"data": "F100000000"},
        "id": 0,
    }
    encrypt_response(payload)
    with pytest.raises(RainbirdApiException, match=r"wrong response"):
        await controller.test_command_support("00")


@freeze_time("2023-01-21 09:32:00")
async def test_cyclic_schedule(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
    sip_data_responses: Callable[[list[str]], None],
) -> None:
    """Test checking for an RPC support."""
    controller = await rainbird_controller()

    api_response("82", modelID=0x0A, protocolRevisionMajor=1, protocolRevisionMinor=3)
    api_response("83", pageNumber=1, setStations=0x1F000000)  # 5 stations
    sip_data_responses(
        [
            "A0000000000400",
            "A000106A0602006401",
            "A000117F0300006400",
            "A00012000300006400",
            "A0006000F0FFFFFFFFFFFF",
            "A00061FFFFFFFFFFFFFFFF",
            "A00062FFFFFFFFFFFFFFFF",
            "A00080001900000000001400000000",
            "A00081000700000000001400000000",
            "A00082000A00000000000000000000",
            "A00083000000000000000000000000",
            "A00084000000000000000000000000",
            "A00085000000000000000000000000",
            "A00086000000000000000000000000",
            "A00087000000000000000000000000",
            "A00088000000000000000000000000",
            "A00089000000000000000000000000",
            "A0008A000000000000000000000000",
        ]
    )

    schedule = await controller.get_schedule()
    assert len(schedule.programs) == 3

    program = schedule.programs[0]
    assert program.program == 0
    assert program.name == "PGM A"
    assert program.frequency == ProgramFrequency.CYCLIC
    assert program.period == 6
    assert program.synchro == 2
    assert program.starts == [datetime.time(4, 0, 0)]
    assert program.duration == datetime.timedelta(minutes=(25 + 20 + 7 + 20 + 10))
    assert program.days_of_week == set()
    assert len(program.durations) == 5
    assert program.durations[0].zone == 1
    assert program.durations[0].duration == datetime.timedelta(minutes=25)
    assert program.durations[0].name == "Zone 1"
    assert program.durations[1].zone == 2
    assert program.durations[1].duration == datetime.timedelta(minutes=20)
    assert program.durations[1].name == "Zone 2"
    assert program.durations[2].zone == 3
    assert program.durations[2].duration == datetime.timedelta(minutes=7)
    assert program.durations[2].name == "Zone 3"
    assert program.durations[3].zone == 4
    assert program.durations[3].duration == datetime.timedelta(minutes=20)
    assert program.durations[3].name == "Zone 4"
    assert program.durations[4].zone == 5
    assert program.durations[4].duration == datetime.timedelta(minutes=10)
    assert program.durations[4].name == "Zone 5"
    events = list(
        program.timeline.overlapping(
            datetime.datetime(2023, 1, 1, 9, 32, 00),
            datetime.datetime(2023, 2, 11, 0, 0, 0),
        )
    )
    assert [val.start for val in events] == [
        datetime.datetime(2023, 1, 17, 4, 0, 0),
        datetime.datetime(2023, 1, 29, 4, 0, 0),
        datetime.datetime(2023, 2, 4, 4, 0, 0),
        datetime.datetime(2023, 2, 10, 4, 0, 0),
    ]
    assert events[0].program_id.name == "PGM A"
    assert events[0].start == datetime.datetime(2023, 1, 17, 4, 0, 0)
    assert events[0].end == datetime.datetime(2023, 1, 17, 5, 22, 0)
    assert events[0].rrule_str == "FREQ=DAILY;INTERVAL=6"

    program = schedule.programs[1]
    assert program.program == 1
    assert program.name == "PGM B"
    assert program.frequency == ProgramFrequency.CUSTOM
    assert program.period is None
    assert program.synchro == 0
    assert program.starts == []
    assert program.duration == datetime.timedelta(seconds=0)
    assert program.days_of_week == set(
        {
            DayOfWeek.MONDAY,
            DayOfWeek.TUESDAY,
            DayOfWeek.WEDNESDAY,
            DayOfWeek.THURSDAY,
            DayOfWeek.FRIDAY,
            DayOfWeek.SATURDAY,
            DayOfWeek.SUNDAY,
        }
    )
    assert len(program.durations) == 0
    assert (
        list(
            program.timeline.overlapping(
                datetime.datetime(2023, 1, 21, 9, 32, 00),
                datetime.datetime(2023, 2, 11, 0, 0, 0),
            )
        )
        == []
    )

    events = list(
        schedule.timeline.overlapping(
            datetime.datetime(2023, 1, 21, 9, 32, 00),
            datetime.datetime(2023, 2, 11, 0, 0, 0),
        )
    )
    assert events[0].program_id.name == "PGM A"
    assert events[0].start == datetime.datetime(2023, 1, 29, 4, 0, 0)
    assert events[0].end == datetime.datetime(2023, 1, 29, 5, 22, 0)


@freeze_time("2023-01-21 09:32:00")
async def test_custom_schedule(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
    sip_data_responses: Callable[[list[str]], None],
) -> None:
    """Test checking for an RPC support."""
    controller = await rainbird_controller()

    api_response("82", modelID=0x0A, protocolRevisionMajor=1, protocolRevisionMinor=3)
    api_response("83", pageNumber=1, setStations=0x1F000000)  # 5 stations
    sip_data_responses(
        [
            "A0000000000400",
            "A00010060602006400",
            "A00011110602006400",
            "A00012000300006400",
            "A0006000F0FFFFFFFFFFFF",
            "A00061FFFFFFFFFFFFFFFF",
            "A00062FFFFFFFFFFFFFFFF",
            "A00080001900000000001400000000",
            "A00081000700000000001400000000",
            "A00082000A00000000000000000000",
            "A00083000000000000000000000000",
            "A00084000000000000000000000000",
            "A00085000000000000000000000000",
            "A00086000000000000000000000000",
            "A00087000000000000000000000000",
            "A00088000000000000000000000000",
            "A00089000000000000000000000000",
            "A0008A000000000000000000000000",
        ]
    )

    schedule = await controller.get_schedule()
    assert len(schedule.programs) == 3

    program = schedule.programs[0]
    assert program.program == 0
    assert program.name == "PGM A"
    assert program.frequency == ProgramFrequency.CUSTOM
    assert program.period is None
    assert program.synchro == 2
    assert program.starts == [datetime.time(4, 0, 0)]
    assert program.duration == datetime.timedelta(minutes=(25 + 20 + 7 + 20 + 10))
    assert program.days_of_week == set({DayOfWeek.MONDAY, DayOfWeek.TUESDAY})
    assert len(program.durations) == 5
    assert program.durations[0].zone == 1
    assert program.durations[0].duration == datetime.timedelta(minutes=25)
    assert program.durations[1].zone == 2
    assert program.durations[1].duration == datetime.timedelta(minutes=20)
    assert program.durations[2].zone == 3
    assert program.durations[2].duration == datetime.timedelta(minutes=7)
    assert program.durations[3].zone == 4
    assert program.durations[3].duration == datetime.timedelta(minutes=20)
    assert program.durations[4].zone == 5
    assert program.durations[4].duration == datetime.timedelta(minutes=10)
    assert [
        val.start
        for val in program.timeline.overlapping(
            datetime.datetime(2023, 1, 21, 9, 32, 00),
            datetime.datetime(2023, 2, 11, 0, 0, 0),
        )
    ] == [
        datetime.datetime(2023, 1, 30, 4, 0, 0),
        datetime.datetime(2023, 1, 31, 4, 0, 0),
        datetime.datetime(2023, 2, 6, 4, 0, 0),
        datetime.datetime(2023, 2, 7, 4, 0, 0),
    ]

    program = schedule.programs[1]
    assert program.program == 1
    assert program.name == "PGM B"
    assert program.frequency == ProgramFrequency.CUSTOM
    assert program.period is None
    assert program.synchro == 2
    assert program.starts == []
    assert program.duration == datetime.timedelta(minutes=0)
    assert program.days_of_week == set({DayOfWeek.THURSDAY, DayOfWeek.SUNDAY})
    assert len(program.durations) == 0
    assert (
        list(
            program.timeline.overlapping(
                datetime.datetime(2023, 1, 21, 9, 32, 00),
                datetime.datetime(2023, 2, 11, 0, 0, 0),
            )
        )
        == []
    )


@freeze_time("2023-01-21 09:32:00")
async def test_odd_schedule(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
    sip_data_responses: Callable[[list[str]], None],
) -> None:
    """Test checking for an RPC support."""
    controller = await rainbird_controller()

    api_response("82", modelID=0x0A, protocolRevisionMajor=1, protocolRevisionMinor=3)
    api_response("83", pageNumber=1, setStations=0x1F000000)  # 5 stations
    sip_data_responses(
        [
            "A0000000000400",
            "A00010110602006402",
            "A000117F0300006400",
            "A00012000300006400",
            "A0006000F0FFFFFFFFFFFF",
            "A00061FFFFFFFFFFFFFFFF",
            "A00062FFFFFFFFFFFFFFFF",
            "A00080001900000000001400000000",
            "A00081000700000000001400000000",
            "A00082000A00000000000000000000",
            "A00083000000000000000000000000",
            "A00084000000000000000000000000",
            "A00085000000000000000000000000",
            "A00086000000000000000000000000",
            "A00087000000000000000000000000",
            "A00088000000000000000000000000",
            "A00089000000000000000000000000",
            "A0008A000000000000000000000000",
        ]
    )

    schedule = await controller.get_schedule()
    assert len(schedule.programs) == 3

    program = schedule.programs[0]
    assert program.program == 0
    assert program.frequency == ProgramFrequency.ODD
    assert program.period is None
    assert program.synchro == 2
    assert program.starts == [datetime.time(4, 0, 0)]
    assert program.duration == datetime.timedelta(minutes=(25 + 20 + 7 + 20 + 10))
    assert program.days_of_week == set()
    assert len(program.durations) == 5
    assert program.durations[0].zone == 1
    assert program.durations[0].duration == datetime.timedelta(minutes=25)
    assert program.durations[1].zone == 2
    assert program.durations[1].duration == datetime.timedelta(minutes=20)
    assert program.durations[2].zone == 3
    assert program.durations[2].duration == datetime.timedelta(minutes=7)
    assert program.durations[3].zone == 4
    assert program.durations[3].duration == datetime.timedelta(minutes=20)
    assert program.durations[4].zone == 5
    assert program.durations[4].duration == datetime.timedelta(minutes=10)
    assert [
        val.start
        for val in program.timeline.overlapping(
            datetime.datetime(2023, 1, 21, 9, 32, 00),
            datetime.datetime(2023, 2, 4, 0, 0, 0),
        )
    ] == [
        datetime.datetime(2023, 1, 25, 4, 0, 0),
        datetime.datetime(2023, 1, 27, 4, 0, 0),
        datetime.datetime(2023, 1, 29, 4, 0, 0),
        datetime.datetime(2023, 1, 31, 4, 0, 0),
        datetime.datetime(2023, 2, 1, 4, 0, 0),
        datetime.datetime(2023, 2, 3, 4, 0, 0),
    ]


@freeze_time("2023-01-21 09:32:00")
async def test_even_schedule(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
    sip_data_responses: Callable[[list[str]], None],
) -> None:
    """Test checking for an RPC support."""
    controller = await rainbird_controller()

    api_response("82", modelID=0x0A, protocolRevisionMajor=1, protocolRevisionMinor=3)
    api_response("83", pageNumber=1, setStations=0x1F000000)  # 5 stations
    sip_data_responses(
        [
            "A0000000000400",
            "A00010110602006403",
            "A000117F0300006400",
            "A00012000300006400",
            "A0006000F0FFFFFFFFFFFF",
            "A00061FFFFFFFFFFFFFFFF",
            "A00062FFFFFFFFFFFFFFFF",
            "A00080001900000000001400000000",
            "A00081000700000000001400000000",
            "A00082000A00000000000000000000",
            "A00083000000000000000000000000",
            "A00084000000000000000000000000",
            "A00085000000000000000000000000",
            "A00086000000000000000000000000",
            "A00087000000000000000000000000",
            "A00088000000000000000000000000",
            "A00089000000000000000000000000",
            "A0008A000000000000000000000000",
        ]
    )

    schedule = await controller.get_schedule()
    assert len(schedule.programs) == 3

    program = schedule.programs[0]
    assert program.program == 0
    assert program.frequency == ProgramFrequency.EVEN
    assert program.period is None
    assert program.synchro == 2
    assert program.starts == [datetime.time(4, 0, 0)]
    assert program.duration == datetime.timedelta(minutes=(25 + 20 + 7 + 20 + 10))
    assert program.days_of_week == set()
    assert len(program.durations) == 5
    assert program.durations[0].zone == 1
    assert program.durations[0].duration == datetime.timedelta(minutes=25)
    assert program.durations[1].zone == 2
    assert program.durations[1].duration == datetime.timedelta(minutes=20)
    assert program.durations[2].zone == 3
    assert program.durations[2].duration == datetime.timedelta(minutes=7)
    assert program.durations[3].zone == 4
    assert program.durations[3].duration == datetime.timedelta(minutes=20)
    assert program.durations[4].zone == 5
    assert program.durations[4].duration == datetime.timedelta(minutes=10)
    assert [
        val.start
        for val in program.timeline.overlapping(
            datetime.datetime(2023, 1, 1, 9, 32, 00),
            datetime.datetime(2023, 2, 4, 0, 0, 0),
        )
    ] == [
        datetime.datetime(2023, 1, 14, 4, 0, 0),
        datetime.datetime(2023, 1, 16, 4, 0, 0),
        datetime.datetime(2023, 1, 18, 4, 0, 0),
        datetime.datetime(2023, 1, 20, 4, 0, 0),
        datetime.datetime(2023, 1, 26, 4, 0, 0),
        datetime.datetime(2023, 1, 28, 4, 0, 0),
        datetime.datetime(2023, 1, 30, 4, 0, 0),
        datetime.datetime(2023, 2, 2, 4, 0, 0),
    ]


@freeze_time("2023-01-21 09:32:00")
async def test_custom_schedule_by_zone(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
    sip_data_responses: Callable[[list[str]], None],
) -> None:
    """Test checking for an RPC support."""
    controller = await rainbird_controller()

    api_response("82", modelID=0x0A, protocolRevisionMajor=1, protocolRevisionMinor=3)
    api_response("83", pageNumber=1, setStations=0x1F000000)  # 5 stations
    sip_data_responses(
        [
            "A0000000000300",
            "A00010060602006400",
            "A00011110602006400",
            "A00012000300006400",
            "A0006000F0FFFFFFFFFFFF",
            "A00061FFFFFFFFFFFFFFFF",
            "A00062FFFFFFFFFFFFFFFF",
            "A00080001900000000001400000000",
            "A00081000700000000001400000000",
            "A00082000A00000000000000000000",
            "A00083000000000000000000000000",
            "A00084000000000000000000000000",
            "A00085000000000000000000000000",
            "A00086000000000000000000000000",
            "A00087000000000000000000000000",
            "A00088000000000000000000000000",
            "A00089000000000000000000000000",
            "A0008A000000000000000000000000",
        ]
    )

    schedule = await controller.get_schedule()
    assert schedule.controller_info.rain_delay == 3
    assert len(schedule.programs) == 3
    program = schedule.programs[0]
    assert program.program == 0
    assert program.name == "PGM A"
    assert program.frequency == ProgramFrequency.CUSTOM
    assert program.days_of_week == set({DayOfWeek.MONDAY, DayOfWeek.TUESDAY})
    assert len(program.durations) == 5
    assert program.durations[0].zone == 1
    assert program.durations[0].duration == datetime.timedelta(minutes=25)
    assert program.durations[1].zone == 2
    assert program.durations[1].duration == datetime.timedelta(minutes=20)
    assert program.durations[2].zone == 3
    assert program.durations[2].duration == datetime.timedelta(minutes=7)
    assert program.durations[3].zone == 4
    assert program.durations[3].duration == datetime.timedelta(minutes=20)
    assert program.durations[4].zone == 5
    assert program.durations[4].duration == datetime.timedelta(minutes=10)
    events = list(
        program.zone_timeline.overlapping(
            datetime.datetime(2023, 1, 21, 9, 32, 00),
            datetime.datetime(2023, 2, 11, 0, 0, 0),
        )
    )
    assert events
    # First date
    assert events[0].program_id.name == "PGM A: Zone 1"
    assert events[0].start == datetime.datetime(2023, 1, 24, 4, 0, 0)
    assert events[0].end == datetime.datetime(2023, 1, 24, 4, 25, 0)
    assert events[0].rrule_str == "FREQ=WEEKLY;BYDAY=MO,TU"
    assert events[1].program_id.name == "PGM A: Zone 2"
    assert events[1].start == datetime.datetime(2023, 1, 24, 4, 25, 0)
    assert events[1].end == datetime.datetime(2023, 1, 24, 4, 45, 0)
    assert events[1].rrule_str == "FREQ=WEEKLY;BYDAY=MO,TU"
    assert events[2].program_id.name == "PGM A: Zone 3"
    assert events[2].start == datetime.datetime(2023, 1, 24, 4, 45, 0)
    assert events[2].end == datetime.datetime(2023, 1, 24, 4, 52, 0)
    assert events[3].program_id.name == "PGM A: Zone 4"
    assert events[3].start == datetime.datetime(2023, 1, 24, 4, 52, 0)
    assert events[3].end == datetime.datetime(2023, 1, 24, 5, 12, 0)
    assert events[4].program_id.name == "PGM A: Zone 5"
    assert events[4].start == datetime.datetime(2023, 1, 24, 5, 12, 0)
    assert events[4].end == datetime.datetime(2023, 1, 24, 5, 22, 0)
    # Continues to next date
    assert events[5].program_id.name == "PGM A: Zone 1"
    assert events[5].start == datetime.datetime(2023, 1, 30, 4, 0, 0)
    assert events[5].end == datetime.datetime(2023, 1, 30, 4, 25, 0)


@freeze_time("2023-01-25 20:00:00")
async def test_custom_schedule_in_past(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
    sip_data_responses: Callable[[list[str]], None],
) -> None:
    """Test checking for an RPC support."""
    controller = await rainbird_controller()

    api_response("82", modelID=0x0A, protocolRevisionMajor=1, protocolRevisionMinor=3)
    api_response("83", pageNumber=1, setStations=0x1F000000)  # 5 stations
    sip_data_responses(
        [
            "A0000000000000",
            "A00010110605006401",
            "A000117F0300006400",
            "A00012000300006400",
            "A0006000F0FFFFFFFFFFFF",
            "A00061FFFFFFFFFFFFFFFF",
            "A00062FFFFFFFFFFFFFFFF",
            "A00080001900000000001400000000",
            "A00081000700000000001400000000",
            "A00082000A00000000000000000000",
            "A00083000000000000000000000000",
            "A00084000000000000000000000000",
            "A00085000000000000000000000000",
            "A00086000000000000000000000000",
            "A00087000000000000000000000000",
            "A00088000000000000000000000000",
            "A00089000000000000000000000000",
            "A0008A000000000000000000000000",
        ]
    )

    schedule = await controller.get_schedule()
    assert len(schedule.programs) == 3

    program = schedule.programs[0]
    assert program.program == 0
    assert program.name == "PGM A"
    assert program.frequency == ProgramFrequency.CYCLIC
    assert program.synchro == 5
    assert program.period == 6
    assert len(program.durations) == 5
    events = list(
        schedule.timeline.overlapping(
            datetime.datetime(2023, 1, 1, 0, 0, 00),
            datetime.datetime(2023, 2, 6, 0, 0, 0),
        )
    )
    assert events
    assert [event.start for event in events] == [
        datetime.datetime(2023, 1, 24, 4, 0, 0),
        datetime.datetime(2023, 1, 30, 4, 0, 0),
        datetime.datetime(2023, 2, 5, 4, 0, 0),
    ]
