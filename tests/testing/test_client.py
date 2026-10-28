"""Tests for high-level local controller client commands using the testing server."""

import datetime
from collections.abc import AsyncIterator

import aiohttp
import pytest

from pyrainbird import async_client
from pyrainbird.async_client import AsyncRainbirdController
from pyrainbird.const import DayOfWeek, ProgramFrequency
from pyrainbird.testing.server import RainbirdFakeServer

PASSWORD = "keepsecret"


@pytest.fixture
async def fake_server() -> AsyncIterator[RainbirdFakeServer]:
    """Fixture to start and stop the RainbirdFakeServer."""
    async with RainbirdFakeServer(password=PASSWORD) as server:
        yield server


@pytest.fixture
async def controller(
    fake_server: RainbirdFakeServer,
) -> AsyncIterator[AsyncRainbirdController]:
    """Fixture to create the client controller pointing to the fake server."""
    async with aiohttp.ClientSession() as session:
        controller = await async_client.create_controller(
            session, fake_server.host_port, PASSWORD
        )
        yield controller


@pytest.mark.asyncio
async def test_get_model_and_version(
    controller: AsyncRainbirdController,
) -> None:
    """Test getting model and version capability."""
    model_and_ver = await controller.get_model_and_version()
    assert model_and_ver.model == 5
    assert model_and_ver.model_code == "ESP_TM2"
    assert model_and_ver.major == 1
    assert model_and_ver.minor == 3


@pytest.mark.asyncio
async def test_get_serial_number(
    controller: AsyncRainbirdController,
) -> None:
    """Test getting serial number capability."""
    serial = await controller.get_serial_number()
    assert serial == 0x12635436566


@pytest.mark.asyncio
async def test_rain_delay(
    fake_server: RainbirdFakeServer, controller: AsyncRainbirdController
) -> None:
    """Test reading and setting rain delay capability."""
    fake_server.device.rain_delay = 2
    delay = await controller.get_rain_delay()
    assert delay == 2

    await controller.set_rain_delay(5)
    assert fake_server.device.rain_delay == 5


@pytest.mark.asyncio
async def test_get_zone_state(
    fake_server: RainbirdFakeServer, controller: AsyncRainbirdController
) -> None:
    """Test reading active/inactive zone states capability."""
    fake_server.device.zone_states = {"00": "BF0001000000"}  # Active zone 1
    zone_state = await controller.get_zone_state(1)
    assert zone_state is True

    fake_server.device.zone_states = {"00": "BF0000000000"}  # Inactive zone 1
    zone_state = await controller.get_zone_state(1)
    assert zone_state is False


@pytest.mark.asyncio
async def test_firmware_update_status(
    fake_server: RainbirdFakeServer, controller: AsyncRainbirdController
) -> None:
    """Test getting firmware update status."""
    fake_server.device.update_status = 0
    fake_server.device.lnk_progress = 50
    fake_server.device.unv_progress = 75

    status = await controller.get_firmware_update_status()
    assert status.update_status == 0
    assert status.lnk_progress == 50
    assert status.unv_progress == 75


@pytest.mark.asyncio
async def test_request_firmware_update(
    controller: AsyncRainbirdController,
) -> None:
    """Test triggering a firmware update."""
    res = await controller.request_firmware_update(
        lnk_update_url="http://test/lnk",
        unv_update_url="http://test/unv",
    )
    assert res == {"status": "OK"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_name", "expected_code", "expected_programs", "expected_zone_schedules"),
    [
        ("ESP_RZXe", "ESP_RZXe", 0, 8),
        ("ESP_RZXe2", "ESP_RZXe2", 0, 8),
        ("ST8X_WF", "ST8X_WF", 0, 8),
        ("ST8X_WF2", "ST8X_WF2", 0, 8),
        ("ESP_TM2", "ESP_TM2", 3, 0),
        ("ESP_ME", "ESP_ME", 4, 0),
        ("ESP_TM2v3", "ESP_TM2v3", 3, 0),
        ("ESP_ME3", "ESP_ME3", 4, 0),
        ("RC2", "RC2", 3, 0),
    ],
)
async def test_client_across_common_device_models(
    model_name: str,
    expected_code: str,
    expected_programs: int,
    expected_zone_schedules: int,
) -> None:
    """Verify AsyncRainbirdController end-to-end across LCR, legacy SIP, and Universal CDT controllers."""
    async with (
        RainbirdFakeServer(password=PASSWORD, model=model_name) as server,
        aiohttp.ClientSession() as session,
    ):
        ctrl = await async_client.create_controller(session, server.host_port, PASSWORD)
        mv = await ctrl.get_model_and_version()
        assert mv.model_code == expected_code

        stations = await ctrl.get_available_stations()
        assert len(stations.active_set) > 0

        await ctrl.set_current_time(datetime.time(9, 45, 0))
        assert await ctrl.get_current_time() == datetime.time(9, 45, 0)

        await ctrl.set_current_date(datetime.date(2026, 6, 15))
        assert await ctrl.get_current_date() == datetime.date(2026, 6, 15)

        await ctrl.set_rain_delay(4)
        assert await ctrl.get_rain_delay() == 4

        await ctrl.irrigate_zone(2, 5)
        assert await ctrl.get_zone_state(2) is True
        await ctrl.stop_irrigation()
        assert await ctrl.get_zone_state(2) is False

        sched = await ctrl.get_schedule()
        assert len(sched.programs) == expected_programs
        assert len(sched.zone_schedules) == expected_zone_schedules

        wifi = await ctrl.get_wifi_params()
        assert wifi.mac_address is not None
        net = await ctrl.get_network_status()
        assert net.network_up is True
        settings = await ctrl.get_settings()
        assert settings.num_programs > 0


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["ESP_RZXe", "ESP_RZXe2", "ST8X_WF", "ST8X_WF2"])
async def test_lcr_zone_schedule_roundtrip(model_name: str) -> None:
    """Verify set_zone_schedule and get_schedule roundtrip on LCR controllers."""
    async with (
        RainbirdFakeServer(password=PASSWORD, model=model_name) as server,
        aiohttp.ClientSession() as session,
    ):
        ctrl = await async_client.create_controller(session, server.host_port, PASSWORD)
        await ctrl.set_zone_schedule(
            zone=1,
            duration=datetime.timedelta(minutes=15),
            starts=[datetime.time(6, 0)],
            frequency=ProgramFrequency.CUSTOM,
            days_of_week={DayOfWeek.MONDAY, DayOfWeek.WEDNESDAY},
        )
        sched = await ctrl.get_schedule()
        assert len(sched.zone_schedules) == 8
        assert sched.zone_schedules[1].duration == datetime.timedelta(minutes=15)
        assert sched.zone_schedules[1].starts == [datetime.time(6, 0)]
        assert sched.zone_schedules[1].days_of_week == {
            DayOfWeek.MONDAY,
            DayOfWeek.WEDNESDAY,
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["ESP_RZXe2", "ST8X_WF2", "ESP_TM2v3"])
async def test_combined_controller_state(model_name: str) -> None:
    """Verify get_combined_controller_state on controllers supporting 0x4C."""
    async with (
        RainbirdFakeServer(password=PASSWORD, model=model_name) as server,
        aiohttp.ClientSession() as session,
    ):
        ctrl = await async_client.create_controller(session, server.host_port, PASSWORD)
        await ctrl.set_rain_delay(4)
        state = await ctrl.get_combined_controller_state()
        assert state.delay_setting == 4
