"""Tests for UDP local controller discovery."""

import socket

import pytest

from pyrainbird.discovery import async_discover_devices
from pyrainbird.testing.server import RainbirdFakeServer


def _get_free_udp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.mark.asyncio
async def test_async_discover_devices_success() -> None:
    """Test discovering a fake Rainbird controller via UDP."""
    resp_port = _get_free_udp_port()

    async with RainbirdFakeServer(
        mac_address="44:2c:05:00:11:22",
        uuid_str="123e4567-e89b-12d3-a456-426614174000",
        response_udp_port=resp_port,
    ) as server:
        udp_port = server._udp_transport.get_extra_info("sockname")[1]

        devices = await async_discover_devices(
            timeout=0.2,
            broadcast_address="127.0.0.1",
            broadcast_ports=(udp_port,),
            listen_port=resp_port,
        )

        assert len(devices) == 1
        dev = devices[0]
        assert dev.ip_address == "127.0.0.1"
        assert dev.mac_address == "442c05001122"
        assert dev.uuid == "123e4567-e89b-12d3-a456-426614174000"
        assert len(dev.raw_responses) == 2


@pytest.mark.asyncio
async def test_async_discover_devices_listen_port_busy() -> None:
    """Test discovery continues gracefully when the upgraded listen port is already busy."""
    resp_port = _get_free_udp_port()

    # Occupy the port exclusively
    busy_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    busy_sock.bind(("0.0.0.0", resp_port))

    try:
        async with RainbirdFakeServer(
            mac_address="44:2c:05:00:11:22",
            uuid_str="123e4567-e89b-12d3-a456-426614174000",
            response_udp_port=resp_port,
        ) as server:
            udp_port = server._udp_transport.get_extra_info("sockname")[1]

            devices = await async_discover_devices(
                timeout=0.2,
                broadcast_address="127.0.0.1",
                broadcast_ports=(udp_port,),
                listen_port=resp_port,
            )

            # Even though upgraded response listener failed to bind, legacy response on ephemeral port succeeds
            assert len(devices) == 1
            dev = devices[0]
            assert dev.ip_address == "127.0.0.1"
            assert dev.mac_address == "442c05001122"
    finally:
        busy_sock.close()


@pytest.mark.asyncio
async def test_async_discover_devices_timeout_no_devices() -> None:
    """Test discovery with no responsive devices returns an empty list."""
    unused_port = _get_free_udp_port()
    devices = await async_discover_devices(
        timeout=0.1,
        broadcast_address="127.0.0.1",
        broadcast_ports=(unused_port,),
        listen_port=0,
    )
    assert devices == []
