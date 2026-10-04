"""Local network discovery for Rain Bird controllers."""

import asyncio
import logging
import socket
from collections.abc import Callable
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)

DISCOVERY_PAYLOAD = b"RBD-ANDROID"
DEFAULT_BROADCAST_PORTS = (33667, 33668)
DEFAULT_LISTEN_PORT = 33668


@dataclass
class DiscoveredDevice:
    """A Rain Bird device discovered on the local network."""

    ip_address: str
    mac_address: str | None = None
    uuid: str | None = None
    raw_responses: list[bytes] = field(default_factory=list)


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    """Protocol to handle UDP discovery responses."""

    def __init__(self, on_response: Callable[[bytes, tuple[str, int]], None]) -> None:
        self.on_response = on_response
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.on_response(data, addr)


async def async_discover_devices(
    timeout: float = 5.0,
    broadcast_address: str = "255.255.255.255",
    broadcast_ports: tuple[int, ...] = DEFAULT_BROADCAST_PORTS,
    listen_port: int = DEFAULT_LISTEN_PORT,
    payload: bytes = DISCOVERY_PAYLOAD,
) -> list[DiscoveredDevice]:
    """Broadcast UDP discovery ping to find controllers on the local network.

    Rain Bird controllers respond to discovery broadcasts in two modes:
    1. Legacy mode: responds back to the sender's ephemeral port with MAC address.
    2. Upgraded mode: responds to port 33668 with device UUID.
    """
    loop = asyncio.get_running_loop()
    devices: dict[str, DiscoveredDevice] = {}

    def handle_response(
        data: bytes, addr: tuple[str, int], is_upgraded: bool = False
    ) -> None:
        ip = addr[0]
        device = devices.setdefault(ip, DiscoveredDevice(ip_address=ip))
        device.raw_responses.append(data)
        decoded = data.decode("utf-8", errors="ignore").strip()
        if decoded:
            if is_upgraded or ("-" in decoded and len(decoded) == 36):
                device.uuid = decoded
            else:
                device.mac_address = decoded

    # Ephemeral broadcast socket for sending ping and receiving legacy responses
    broadcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    broadcast_sock.setblocking(False)

    broadcast_transport, _ = await loop.create_datagram_endpoint(
        lambda: _DiscoveryProtocol(
            lambda data, addr: handle_response(data, addr, is_upgraded=False)
        ),
        sock=broadcast_sock,
    )

    upgraded_transport: asyncio.DatagramTransport | None = None
    if listen_port:
        try:
            upgraded_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            upgraded_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                upgraded_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            upgraded_sock.bind(("0.0.0.0", listen_port))
            upgraded_sock.setblocking(False)
            upgraded_transport, _ = await loop.create_datagram_endpoint(
                lambda: _DiscoveryProtocol(
                    lambda data, addr: handle_response(data, addr, is_upgraded=True)
                ),
                sock=upgraded_sock,
            )
        except OSError as err:
            _LOGGER.warning(
                "Could not bind to port %d for upgraded discovery: %s",
                listen_port,
                err,
            )

    try:
        for port in broadcast_ports:
            broadcast_transport.sendto(payload, (broadcast_address, port))
        await asyncio.sleep(timeout)
    finally:
        broadcast_transport.close()
        if upgraded_transport is not None:
            upgraded_transport.close()

    return list(devices.values())
