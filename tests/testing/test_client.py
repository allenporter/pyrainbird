"""Tests for high-level local controller client commands using the testing server."""

from collections.abc import AsyncIterator

import aiohttp
import pytest

from pyrainbird import async_client
from pyrainbird.async_client import AsyncRainbirdController
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

    # Test alias
    status_alias = await controller.get_fw_update_status()
    assert status_alias == status


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

    # Test alias
    res_alias = await controller.request_fw_update(
        lnk_update_url="http://test/lnk",
        unv_update_url="http://test/unv",
    )
    assert res_alias == {"status": "OK"}
