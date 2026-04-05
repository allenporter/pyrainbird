"""Test for AsyncRainbirdController."""

from __future__ import annotations

import datetime
import itertools
import json
from collections.abc import Awaitable, Callable, Generator, Iterator
from typing import Any
from unittest import mock

import aiohttp
import pytest
from freezegun import freeze_time

from pyrainbird import rainbird
from pyrainbird.async_client import (
    AsyncRainbirdClient,
    AsyncRainbirdController,
    create_controller,
)
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
    RainbirdConnectionError,
    RainbirdDeviceBusyException,
)
from pyrainbird.resources import RAINBIRD_COMMANDS_BY_ID

from .conftest import LENGTH, PASSWORD, REQUEST, RESPONSE, RESULT_DATA, ResponseResult
from .fake_device import FakeRainbirdDevice


@pytest.fixture(autouse=True)
def auto_snapshot_request_log(
    request_log: list[dict[str, Any]], snapshot: Any
) -> Generator[None, None, None]:
    """Automatically snapshot the network requests of every test."""
    yield
    if request_log:
        assert str(request_log) == snapshot
    else:
        assert [] == snapshot


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

    with (
        mock.patch("pyrainbird.async_client._retry_attempts", return_value=1),
        mock.patch("pyrainbird.async_client._retry_delay", return_value=0.01),
    ):
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


async def test_create_controller_tries_insecure_https_first() -> None:
    session = mock.AsyncMock(spec=aiohttp.ClientSession)

    with (
        mock.patch("pyrainbird.async_client.AsyncRainbirdClient") as client_cls,
        mock.patch(
            "pyrainbird.async_client.AsyncRainbirdController.get_model_and_version",
            new=mock.AsyncMock(return_value=ModelAndVersion(0x0A, 1, 3)),
        ),
    ):
        await create_controller(session, "example.com", "password")

    assert client_cls.call_args_list == [
        mock.call(session, mock.ANY, None),
        mock.call(session, "https://example.com/stick", "password", ssl_context=False),
    ]


async def test_create_controller_tries_https_then_http_on_connection_error() -> None:
    session = mock.AsyncMock(spec=aiohttp.ClientSession)

    with (
        mock.patch("pyrainbird.async_client.AsyncRainbirdClient") as client_cls,
        mock.patch(
            "pyrainbird.async_client.AsyncRainbirdController.get_model_and_version",
            new=mock.AsyncMock(
                side_effect=[
                    RainbirdConnectionError("connect error"),
                    ModelAndVersion(0x0A, 1, 3),
                ]
            ),
        ),
    ):
        await create_controller(session, "example.com", "password")

    assert client_cls.call_args_list == [
        mock.call(session, mock.ANY, None),
        mock.call(session, "https://example.com/stick", "password", ssl_context=False),
        mock.call(session, "http://example.com/stick", "password", ssl_context=None),
    ]


async def test_create_controller_does_not_fallback_on_auth_error() -> None:
    session = mock.AsyncMock(spec=aiohttp.ClientSession)

    with (
        mock.patch("pyrainbird.async_client.AsyncRainbirdClient") as client_cls,
        mock.patch(
            "pyrainbird.async_client.AsyncRainbirdController.get_model_and_version",
            new=mock.AsyncMock(side_effect=RainbirdAuthException("bad password")),
        ),
    ):
        with pytest.raises(RainbirdAuthException):
            await create_controller(session, "example.com", "password")

    assert client_cls.call_args_list == [
        mock.call(session, mock.ANY, None),
        mock.call(session, "https://example.com/stick", "password", ssl_context=False),
    ]


async def test_rainbird_client_only_passes_ssl_kwarg_when_configured() -> None:
    session = mock.AsyncMock(spec=aiohttp.ClientSession)

    response = mock.Mock()
    response.raise_for_status = mock.Mock()
    response.read = mock.AsyncMock(return_value=b"raw")

    session.request = mock.AsyncMock(return_value=response)

    coder = mock.Mock()
    coder.encode_command.return_value = b"payload"
    coder.decode_command.return_value = {}

    with mock.patch(
        "pyrainbird.async_client.encryption.PayloadCoder",
        return_value=coder,
    ):
        client = AsyncRainbirdClient(session, "https://example.com/stick", "password")
        await client.request("getModelAndVersion")
        _, request_kwargs = session.request.call_args
        assert "ssl" not in request_kwargs

        session.request.reset_mock()

        insecure_client = AsyncRainbirdClient(
            session,
            "https://example.com/stick",
            "password",
            ssl_context=False,
        )
        await insecure_client.request("getModelAndVersion")
        _, request_kwargs = session.request.call_args
        assert request_kwargs["ssl"] is False


@pytest.fixture(name="encrypt_response")
def mock_encrypt_response(response: ResponseResult) -> Callable[[...], None]:
    """Fixture to encrypt API responses."""

    def _put_result(plaintext: str | dict) -> None:
        if isinstance(plaintext, dict):
            plaintext = json.dumps(plaintext)
        body = encrypt(plaintext, PASSWORD)
        response(aiohttp.web.Response(body=body))

    return _put_result


@pytest.fixture(name="api_response_id")
def api_response_id_fixture() -> Iterator[int]:
    """Provide sequential ids for hardcoded mock responses."""
    return itertools.count(1)


@pytest.fixture(name="api_response")
def mock_api_response(
    encrypt_response: Callable[[str | dict], None],
    api_response_id: Iterator[int],
) -> Callable[[...], None]:
    """Fixture to construct a fake API response."""

    def _put_result(command: str, **kvargs) -> None:
        command_set = RAINBIRD_COMMANDS_BY_ID[command]
        data = rainbird.encode_command(command_set, *kvargs.values())
        encrypt_response(
            {"jsonrpc": "2.0", "result": {"data": data}, "id": next(api_response_id)}
        )

    return _put_result


async def test_get_model_and_version(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    fake_device: FakeRainbirdDevice,
) -> None:
    fake_device.set_model("ESP_TM2v2")
    fake_device.version_major = 1
    fake_device.version_minor = 3
    controller = await rainbird_controller()
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
    assert not model_info.retries


async def test_get_available_stations(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    fake_device: FakeRainbirdDevice,
) -> None:
    fake_device.set_model("ESP_ME")
    fake_device.stations = {1, 2, 3, 4, 5, 6, 7}
    controller = await rainbird_controller()
    stations = await controller.get_available_stations()
    assert stations.active_set == {1, 2, 3, 4, 5, 6, 7}


async def test_get_available_stations_multipage(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    fake_device: FakeRainbirdDevice,
) -> None:
    fake_device.set_model("ESP_2WIRE")
    fake_device.stations = set(range(1, 49))
    controller = await rainbird_controller()
    stations = await controller.get_available_stations()
    assert stations.stations.count == 64
    assert len(stations.active_set) == 48  # 32 from page 0 + 16 from page 1
    assert stations.active_set == set(range(1, 49))


async def test_device_busy_retries(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    rainbird_client: Callable[[], Awaitable[AsyncRainbirdClient]],
    api_response: Callable[[...], Awaitable[None]],
    response: ResponseResult,
) -> None:
    """Test a basic request failure handling with retries."""
    controller = await rainbird_controller()
    api_response("82", modelID=0x09, protocolRevisionMajor=1, protocolRevisionMinor=3)
    result = await controller.get_model_and_version()
    assert result.model_code == "ESP_ME3"
    assert result.model_info.retries

    # Make two attempts then succeed
    response(aiohttp.web.Response(status=503))
    response(aiohttp.web.Response(status=503))
    api_response("83", pageNumber=1, setStations=0x7F000000)

    stations = await controller.get_available_stations()
    assert stations.active_set == {1, 2, 3, 4, 5, 6, 7}


async def test_non_retryable_errors(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    rainbird_client: Callable[[], Awaitable[AsyncRainbirdClient]],
    api_response: Callable[[...], Awaitable[None]],
    response: ResponseResult,
) -> None:
    """Test a basic request failure handling with retries."""
    controller = await rainbird_controller()
    api_response("82", modelID=0x09, protocolRevisionMajor=1, protocolRevisionMinor=3)
    result = await controller.get_model_and_version()
    assert result.model_code == "ESP_ME3"
    assert result.model_info.retries

    # Other types of errors are not retried
    response(aiohttp.web.Response(status=403))
    with pytest.raises(RainbirdAuthException):
        await controller.get_available_stations()


async def test_device_busy_retries_not_enabled(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    rainbird_client: Callable[[], Awaitable[AsyncRainbirdClient]],
    api_response: Callable[[...], Awaitable[None]],
    response: ResponseResult,
) -> None:
    """Test a basic request failure handling for device without retries."""
    controller = await rainbird_controller()
    api_response("82", modelID=0x0A, protocolRevisionMajor=1, protocolRevisionMinor=3)
    result = await controller.get_model_and_version()
    assert result == ModelAndVersion(0x0A, 1, 3)
    assert result.model_code == "ESP_TM2v2"
    assert result.model_name == "ESP-TM2"
    assert not result.model_info.retries

    response(aiohttp.web.Response(status=503))

    with pytest.raises(RainbirdDeviceBusyException):
        await controller.get_available_stations()


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


@freeze_time("2023-01-01 00:00:00")
async def test_get_current_date(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    controller = await rainbird_controller()
    date = datetime.date.today()
    api_response("92", day=date.day, month=date.month, year=date.year)
    assert await controller.get_current_date() == date


@freeze_time("2023-01-01 00:00:00")
async def test_set_current_time(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    api_response: Callable[[...], Awaitable[None]],
) -> None:
    """Test for setting the current time."""
    controller = await rainbird_controller()
    api_response("01", commandEcho="11")
    await controller.set_current_time(datetime.datetime.now().time())


@freeze_time("2023-01-01 00:00:00")
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
    api_response("82", modelID=0x07, protocolRevisionMajor=1, protocolRevisionMinor=3)
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
    api_response("82", modelID=0x07, protocolRevisionMajor=1, protocolRevisionMinor=3)
    for i in range(1, 9):
        for j in range(1, 9):
            mask = (1 << (i - 1)) * 0x1000000
            api_response("BF", pageNumber=0, activeStations=mask)
            assert await controller.get_zone_state(j) == (i == j)


@pytest.mark.parametrize(
    ("sip_data", "active_zones"),
    [
        ("BF0000000000", []),
        ("BF0000010000", [9]),
        ("BF0000000001", [25]),
        ("BF0000000002", [26]),
        ("BF0000000004", [27]),
        ("BF0000381000", [12, 13, 14, 21]),
    ],
)
async def test_get_zone_state_lxivm(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    fake_device: FakeRainbirdDevice,
    sip_data: str,
    active_zones: list[int],
) -> None:
    fake_device.set_model("ESP-Me")
    fake_device.zone_states = {"00": sip_data}
    controller = await rainbird_controller()
    zone_states = await controller.get_zone_states()
    active_states = sorted(list(zone_states.active_set))
    assert active_states == active_zones


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
    assert params.to_dict() == {
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


async def test_get_wifi_params_optional_fields(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    encrypt_response: ResponseResult,
) -> None:
    controller = await rainbird_controller()
    payload = {
        "jsonrpc": "2.0",
        "result": {},
        "id": 1234,
    }
    encrypt_response(payload)
    params = await controller.get_wifi_params()
    assert params.to_dict() == {
        "ap_security": None,
        "ap_timeout_idle": None,
        "ap_timeout_no_lan": None,
        "local_gateway": None,
        "local_ip_address": None,
        "local_netmask": None,
        "mac_address": None,
        "rssi": None,
        "sick_version": None,
        "wifi_password": None,
        "wifi_security": None,
        "wifi_ssid": None,
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


async def test_get_schedule_and_settings_me3(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    response: ResponseResult,
) -> None:
    controller = await rainbird_controller()

    controller = await rainbird_controller()
    payload = {
        "id": 440,
        "jsonrpc": "2.0",
        "result": {
            "settings": {
                "programOptOutMask": "F",
                "country": "AU",
                "numPrograms": 4,
                "code": "3056",
                "globalDisable": True,
                "soilTypes": [0, 0, 0, 0],
                "FlowUnits": [0, 0, 0, 0],
                "FlowRates": [0, 0, 0, 0],
            },
            "12": "920857E9",
            "48": "C801",
            "3B01": "BB01000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
            "3F00": "BF0000000000",
            "schedule": {
                "0C200001000805000000000C0000000000050000000E00070B011500020000000000001500": "8C200000000C00000000000805000000000500FFFF6700080B0115000200000000000015000400000000100E000018150000201C000000000000302A000018150000282300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
                "0C200001000805000000000C0000000000050000000E00070B011500020100010000001500": "8C200000000C00000000000805000000000500FFFF6700080B0115000201000100000015000400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
                "0C200001000805000000000C0000000000050000000E00070B011500020200020000001500": "8C200000000C00000000000805000000000500FFFF6700080B01150002020002000000150004B0040000000000000000000000000000600900000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
                "0C200001000805000000000C0000000000050000000E00070B011500020300030000001500": "8C200000000C00000000000805000000000500FFFF6700080B0115000203000300000015000400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
                # Station with number?
                "0C200001000805000000000C0000000000050000001100070B020A0001000015000B000100001500": "8C200000000C00000000000805000000000500FFFF3F00080B020A00010000150001000000000000000000000000000000000000000000000B0001000015000100000000000000000000000000000000000000000000",
                # Program schedule?
                "0C200001000805000000000C0000000000050000001C00070B0312000100000300110001000003001000020000030000000600": "8C200000000C00000000000805000000000500FFFF4300080B0312000100000300010404030311000100000300010100000210000200000300000006000100000000000000010101010101010000000000000001010101010101",
                "0C200001000805000000000C0000000000050000001700070B041400000D00001800010000030013000100000300": "8C200000000C00000000000805000000000500FFFF2900080B0414000001000D0000010018000100000300022D00320028003500130001000003000104040400",
                # Program station entry?
                "0C200001000805000000000C0000000000050000001200070B011D0003000003000000000000000500": "8C200000000C00000000000805000000000500FFFF4300080B011D0003000003000000000000000500022C01A005A005A005A005A005B400A005A005A005A005A0056801A005A005A005A005A005A005A005A005A005A005A005",
            },
            "3E": "BE00",
            "0B": "8B03080001B1001800",
            "0300": "8300FF030000",
            "4A01": "CA012FAFC19F",
            "3B00": "BB000000000000",
            "62": "E2FF",
            "63": "E30000",
            "status": "good",
            "10": "90133534",
        },
    }
    response(aiohttp.web.json_response(payload))
    result = await controller.get_schedule_and_settings("11:22:33:44:55:66")
    assert result.settings
    settings = result.settings
    assert settings.flow_rates == [0, 0, 0, 0]
    assert settings.flow_units == [0, 0, 0, 0]
    assert settings.code == "3056"
    assert settings.country == "AU"
    assert settings.global_disable
    assert settings.num_programs == 4
    assert settings.program_opt_out_mask == "F"
    assert settings.soil_types == [
        SoilType.NONE,
        SoilType.NONE,
        SoilType.NONE,
        SoilType.NONE,
    ]
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
    with pytest.raises(
        RainbirdApiException, match=r"Unexpected response from Rain Bird device"
    ):
        await controller.test_command_support("00")


@freeze_time("2023-01-21 09:32:00")
async def test_cyclic_schedule(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    fake_device: FakeRainbirdDevice,
) -> None:
    """Test checking for an RPC support."""
    fake_device.set_model("ESP_TM2v2")
    fake_device.stations = {1, 2, 3, 4, 5}
    fake_device.schedule = {
        "0000": "A0000000000400",
        "0010": "A000106A0602006401",
        "0011": "A000117F0300006400",
        "0012": "A00012000300006400",
        "0060": "A0006000F0FFFFFFFFFFFF",
        "0061": "A00061FFFFFFFFFFFFFFFF",
        "0062": "A00062FFFFFFFFFFFFFFFF",
        "0080": "A00080001900000000001400000000",
        "0081": "A00081000700000000001400000000",
        "0082": "A00082000A00000000000000000000",
        "0083": "A00083000000000000000000000000",
        "0084": "A00084000000000000000000000000",
        "0085": "A00085000000000000000000000000",
    }
    controller = await rainbird_controller()

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
    fake_device: FakeRainbirdDevice,
) -> None:
    """Test checking for an RPC support."""
    fake_device.set_model("ESP_TM2v2")
    fake_device.stations = {1, 2, 3, 4, 5}
    fake_device.schedule = {
        "0000": "A0000000000400",
        "0010": "A00010060602006400",
        "0011": "A00011110602006400",
        "0012": "A00012000300006400",
        "0060": "A0006000F0FFFFFFFFFFFF",
        "0061": "A00061FFFFFFFFFFFFFFFF",
        "0062": "A00062FFFFFFFFFFFFFFFF",
        "0080": "A00080001900000000001400000000",
        "0081": "A00081000700000000001400000000",
        "0082": "A00082000A00000000000000000000",
        "0083": "A00083000000000000000000000000",
        "0084": "A00084000000000000000000000000",
        "0085": "A00085000000000000000000000000",
    }
    controller = await rainbird_controller()

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
    fake_device: FakeRainbirdDevice,
) -> None:
    """Test checking for an RPC support."""
    fake_device.set_model("ESP_TM2v2")
    fake_device.stations = {1, 2, 3, 4, 5}
    fake_device.schedule = {
        "0000": "A0000000000400",
        "0010": "A00010110602006402",
        "0011": "A000117F0300006400",
        "0012": "A00012000300006400",
        "0060": "A0006000F0FFFFFFFFFFFF",
        "0061": "A00061FFFFFFFFFFFFFFFF",
        "0062": "A00062FFFFFFFFFFFFFFFF",
        "0080": "A00080001900000000001400000000",
        "0081": "A00081000700000000001400000000",
        "0082": "A00082000A00000000000000000000",
        "0083": "A00083000000000000000000000000",
        "0084": "A00084000000000000000000000000",
        "0085": "A00085000000000000000000000000",
    }
    controller = await rainbird_controller()

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
    fake_device: FakeRainbirdDevice,
) -> None:
    """Test checking for an RPC support."""
    fake_device.set_model("ESP_TM2v2")
    fake_device.stations = {1, 2, 3, 4, 5}
    fake_device.schedule = {
        "0000": "A0000000000400",
        "0010": "A00010110602006403",
        "0011": "A000117F0300006400",
        "0012": "A00012000300006400",
        "0060": "A0006000F0FFFFFFFFFFFF",
        "0061": "A00061FFFFFFFFFFFFFFFF",
        "0062": "A00062FFFFFFFFFFFFFFFF",
        "0080": "A00080001900000000001400000000",
        "0081": "A00081000700000000001400000000",
        "0082": "A00082000A00000000000000000000",
        "0083": "A00083000000000000000000000000",
        "0084": "A00084000000000000000000000000",
        "0085": "A00085000000000000000000000000",
    }
    controller = await rainbird_controller()

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
    fake_device: FakeRainbirdDevice,
) -> None:
    """Test checking for an RPC support."""
    fake_device.set_model("ESP_TM2v2")
    fake_device.stations = {1, 2, 3, 4, 5}
    fake_device.schedule = {
        "0000": "A0000000000300",
        "0010": "A00010060602006400",
        "0011": "A00011110602006400",
        "0012": "A00012000300006400",
        "0060": "A0006000F0FFFFFFFFFFFF",
        "0061": "A00061FFFFFFFFFFFFFFFF",
        "0062": "A00062FFFFFFFFFFFFFFFF",
        "0080": "A00080001900000000001400000000",
        "0081": "A00081000700000000001400000000",
        "0082": "A00082000A00000000000000000000",
        "0083": "A00083000000000000000000000000",
        "0084": "A00084000000000000000000000000",
        "0085": "A00085000000000000000000000000",
    }
    controller = await rainbird_controller()

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
    fake_device: FakeRainbirdDevice,
) -> None:
    """Test checking for an RPC support."""
    fake_device.set_model("ESP_TM2v2")
    fake_device.stations = {1, 2, 3, 4, 5}
    fake_device.schedule = {
        "0000": "A0000000000000",
        "0010": "A00010110605006401",
        "0011": "A000117F0300006400",
        "0012": "A00012000300006400",
        "0060": "A0006000F0FFFFFFFFFFFF",
        "0061": "A00061FFFFFFFFFFFFFFFF",
        "0062": "A00062FFFFFFFFFFFFFFFF",
        "0080": "A00080001900000000001400000000",
        "0081": "A00081000700000000001400000000",
        "0082": "A00082000A00000000000000000000",
        "0083": "A00083000000000000000000000000",
        "0084": "A00084000000000000000000000000",
        "0085": "A00085000000000000000000000000",
    }
    controller = await rainbird_controller()

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


@freeze_time("2023-01-25 20:00:00")
async def test_get_schedule_parse_failure(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    fake_device: FakeRainbirdDevice,
) -> None:
    """Test a schedule that fails to parse."""
    fake_device.set_model("ESP_TM2v2")
    fake_device.stations = {1, 2, 3, 4, 5}
    fake_device.schedule = {
        "0000": "A0000080",
        "0010": "A00010",
        "0011": "A00011",
        "0012": "A00012",
        "0060": "A00060",
        "0061": "A00061",
        "0062": "A00062",
        "0080": "A00080",
        "0081": "A00081",
        "0082": "A00082",
        "0083": "A00083",
        "0084": "A00084",
        "0085": "A00085",
    }
    controller = await rainbird_controller()

    schedule = await controller.get_schedule()
    assert len(schedule.programs) == 0


async def test_get_schedule_esp_me_8_zones(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    fake_device: FakeRainbirdDevice,
) -> None:
    """Test get_schedule for ESP-Me with 8-zone capability."""
    fake_device.set_model("ESP-Me")
    # ESP_Me: max_programs=4, max_stations=22
    fake_device.stations = set(range(1, 9))

    schedule_data = {
        "0000": "A0000000000400",  # state: delay=0, snooze=0, rain=4 (disabled/unknown)
        "0010": "A00010000000000000",  # PGM A
        "0011": "A00011000000000000",  # PGM B
        "0012": "A00012000000000000",  # PGM C
        "0013": "A00013000000000000",  # PGM D
        "0060": "A00060FFFFFFFF",  # No starts
        "0061": "A00061FFFFFFFF",
        "0062": "A00062FFFFFFFF",
        "0063": "A00063FFFFFFFF",
        "0080": "A00080" + "000A000000000000" + "0005000000000000",  # Z1:P1=10, Z2:P1=5
        "0081": "A00081" + "0014000000000000" + "0000000000000000",  # Z3:P1=20, Z4:0
        "0082": "A00082" + "0000000000000000" + "0000000000000000",  # Z5:0, Z6:0
        "0083": "A00083"
        + "000F000000000000"
        + "000A000000000000",  # Z7:P1=15, Z8:P1=10
    }
    # Add empty responses for pages 0x84 to 0x8A (total 11 pages)
    for page in range(0x84, 0x8B):
        schedule_data["00%02X" % page] = "A000" + ("%02X" % page) + ("00" * 16)

    fake_device.schedule = schedule_data
    controller = await rainbird_controller()

    schedule = await controller.get_schedule()

    # Verify we requested 20 schedule commands in total
    # 1 (state) + 4 (program details) + 4 (start times) + 11 (zone pages) = 20
    # Plus discovery: 82, 83 = 22 total requests.
    requests = [
        r for r in fake_device.request_log if type(r).__name__ == "RequestLogEntry"
    ]
    assert len(requests) == 22

    assert len(schedule.programs) == 4
    # Check durations for PGM A (program 0)
    durations = {d.zone: d.duration for d in schedule.programs[0].durations}
    assert durations[1] == datetime.timedelta(minutes=10)
    assert durations[2] == datetime.timedelta(minutes=5)
    assert durations[3] == datetime.timedelta(minutes=20)
    assert durations[7] == datetime.timedelta(minutes=15)
    assert durations[8] == datetime.timedelta(minutes=10)


@freeze_time("2023-01-01 00:00:00")
async def test_get_schedule_non_program_based(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    fake_device: FakeRainbirdDevice,
) -> None:
    """Test get_schedule for a non-program based device (ESP-RZXe)."""
    fake_device.set_model("ESP_RZXe")
    # Active zones: 1, 3, 5
    fake_device.stations = {1, 3, 5}

    fake_device.schedule = {
        "0000": "A000000000",  # state (10 chars for RZX)
        "0001": "A000010A33FFFFFFFFFF007F0000",  # Z1: 10m, start 08:30, CUSTOM (00), all days (0x7F)
        "0003": "A00003143CFFFFFFFFFF007F0000",  # Z3: 20m, start 10:00, CUSTOM (00), all days (0x7F)
        "0005": "A000051E4CFFFFFFFFFF007F0000",  # Z5: 30m, start 12:40, CUSTOM (00), all days (0x7F)
    }

    controller = await rainbird_controller()

    schedule = await controller.get_schedule()

    # Requests: 82, 83 + 1 (00) + 3 commands = 6 total payload requests
    requests = [
        r for r in fake_device.request_log if type(r).__name__ == "RequestLogEntry"
    ]
    assert len(requests) == 6

    # Legacy programs should be completely empty
    assert len(schedule.programs) == 0

    # LCR zones should be strictly 3 elements
    assert len(schedule.zone_schedules) == 3

    # Verify zone runtime data propagated natively
    assert schedule.zone_schedules[1].duration == datetime.timedelta(minutes=10)
    assert schedule.zone_schedules[1].starts == [datetime.time(8, 30)]

    assert schedule.zone_schedules[3].duration == datetime.timedelta(minutes=20)
    assert schedule.zone_schedules[3].starts == [datetime.time(10, 0)]

    assert schedule.zone_schedules[5].duration == datetime.timedelta(minutes=30)
    assert schedule.zone_schedules[5].starts == [datetime.time(12, 40)]

    # Test timeline iterates over the active zones natively!
    tz = datetime.timezone.utc
    events = list(
        schedule.timeline_tz(tz).overlapping(
            datetime.datetime(2023, 1, 1, 0, 0, 0, tzinfo=tz),
            datetime.datetime(2023, 1, 2, 0, 0, 0, tzinfo=tz),
        )
    )

    # 3 active zones, triggering once per day, should yield 3 events per day!
    assert len(events) == 3
    assert events[0].start == datetime.datetime(2023, 1, 1, 8, 30, 0, tzinfo=tz)
    assert events[0].end == datetime.datetime(2023, 1, 1, 8, 40, 0, tzinfo=tz)
    assert events[0].program_id.zone == 1

    assert events[1].start == datetime.datetime(2023, 1, 1, 10, 0, 0, tzinfo=tz)
    assert events[1].end == datetime.datetime(2023, 1, 1, 10, 20, 0, tzinfo=tz)
    assert events[1].program_id.zone == 3

    assert events[2].start == datetime.datetime(2023, 1, 1, 12, 40, 0, tzinfo=tz)
    assert events[2].end == datetime.datetime(2023, 1, 1, 13, 10, 0, tzinfo=tz)
    assert events[2].program_id.zone == 5


async def test_get_schedule_tm2_12_zones(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    fake_device: FakeRainbirdDevice,
) -> None:
    fake_device.set_model("ESP_TM2v2")
    # Available stations mock = 12 zones active
    fake_device.stations = set(range(1, 13))

    schedule_data = {
        "0000": "A0000000000000",
        "0010": "A0001000000000000000",
        "0011": "A0001100000000000000",
        "0012": "A0001200000000000000",
        "0060": "A00060FFFFFFFF",
        "0061": "A00061FFFFFFFF",
        "0062": "A00062FFFFFFFF",
    }
    for page in range(0x80, 0x86):
        schedule_data["00%02X" % page] = "A000" + ("%02X" % page) + ("00" * 12)

    fake_device.schedule = schedule_data
    controller = await rainbird_controller()

    schedule = await controller.get_schedule()
    # Verify the schedule
    assert len(schedule.programs) == 3
    assert [program.program for program in schedule.programs] == [0, 1, 2]

    # 2 initial (Model, Stations) + 1 Global + 3 ProgramInfo + 3 StartTimes + 6 Runtimes = 15 total requests.
    requests = [
        r for r in fake_device.request_log if type(r).__name__ == "RequestLogEntry"
    ]
    assert len(requests) == 15


async def test_get_schedule_unknown_model_fallback(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    fake_device: FakeRainbirdDevice,
) -> None:
    # Unknown model ID
    fake_device.model_code = 0x88
    fake_device.version_major = 1
    fake_device.version_minor = 3
    fake_device.stations = set(range(1, 9))  # 8 zones active

    schedule_data = {
        "0000": "A0000000000000",
    }
    # Unknown models fall back to max_programs=0, triggering the LCR zone loop.
    # It will request the 8 active zones.
    for zone in range(1, 9):
        schedule_data["00%02X" % zone] = (
            "A0000" + ("%X" % zone) + "0A33FFFFFFFFFF007F0000"
        )

    fake_device.schedule = schedule_data
    controller = await rainbird_controller()

    schedule = await controller.get_schedule()

    assert len(schedule.programs) == 0
    # 2 initial (Model, Stations) + 1 Global + 8 Zone Pages = 11 requests
    requests = [
        r for r in fake_device.request_log if type(r).__name__ == "RequestLogEntry"
    ]
    assert len(requests) == 11


async def test_get_schedule_lxme2_bit_collision(
    rainbird_controller: Callable[[], Awaitable[AsyncRainbirdController]],
    fake_device: FakeRainbirdDevice,
) -> None:
    # LXME2 (Model 0x0C): max_programs=40, max_stations=22
    fake_device.model_code = 0x0C
    fake_device.version_major = 1
    fake_device.version_minor = 3
    fake_device.stations = set(range(1, 17))

    schedule_data = {"0000": "A0000000000000"}

    # 40 programs * 2 commands (0x10-0x37 for info, 0x60-0x87 for start times) = 80 commands
    # Plus 11 zones pages = 91 commands
    for i in range(91):
        # We don't want to actually populate all 91 keys manually in this test.
        # Since it only tests bit collision logic via mocked requests, we can just intercept the mock process.
        # However, fake_device expects all keys to be present. We will use a default dict for fake_device in this specific test.
        pass

    class DefaultScheduleDict(dict):
        def __contains__(self, item: Any) -> bool:
            return True

        def __getitem__(self, key: Any) -> Any:
            return "A00099"  # Unrecognized format skips decoding

    schedule_data = DefaultScheduleDict({"0000": "A0000000000000"})
    fake_device.schedule = schedule_data

    controller = await rainbird_controller()

    with mock.patch.object(
        controller, "_process_command", wraps=controller._process_command
    ) as mock_process:
        await controller.get_schedule()

    requests = [
        call.args[2]
        for call in mock_process.call_args_list
        if call.args[1] == "RetrieveScheduleRequest"
    ]

    # Prove the bug by counting duplicate occurrences
    # program index 16 evaluates to 0x10 | 16 = 0x10 (decimal 16). We expect 16 twice.
    assert requests.count(16) == 2

    # Program index 32 evaluating to 0x60 | 32 = 0x60 (decimal 96). We expect 96 twice.
    assert requests.count(96) == 2
