"""Async UDP and HTTP Server for Simulated Rain Bird Device."""

import asyncio
import json
import logging

from aiohttp import web

from pyrainbird.encryption import encrypt
from .device import FakeRainbirdDevice

_LOGGER = logging.getLogger(__name__)


class RainbirdUDPDiscoveryProtocol(asyncio.DatagramProtocol):
    """Protocol to handle UDP discovery broadcasts."""

    def __init__(
        self, mac_address: str, uuid_str: str, response_udp_port: int = 33668
    ) -> None:
        self.mac_address = mac_address
        self.uuid_str = uuid_str
        self.response_udp_port = response_udp_port
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            message = data.decode("utf-8", errors="ignore").strip()
            if "RBD-ANDROID" in message:
                _LOGGER.info("Received UDP discovery ping from %s: %s", addr, message)

                # 1. Legacy Response: MAC address string to ephemeral sender port
                mac_hex = self.mac_address.replace(":", "").replace("-", "").lower()
                if self.transport:
                    self.transport.sendto(mac_hex.encode("utf-8"), addr)
                    _LOGGER.info("Sent legacy response to %s: %s", addr, mac_hex)

                    # 2. Upgraded Response: UUID string to port response_udp_port of sender's IP
                    self.transport.sendto(
                        self.uuid_str.encode("utf-8"), (addr[0], self.response_udp_port)
                    )
                    _LOGGER.info(
                        "Sent upgraded response to %s:%d: %s",
                        addr[0],
                        self.response_udp_port,
                        self.uuid_str,
                    )
        except Exception as e:
            _LOGGER.exception("Error in UDP discovery handler: %s", e)


class RainbirdFakeServer:
    """Combines UDP discovery and HTTP stick JSON-RPC servers."""

    def __init__(
        self,
        mac_address: str = "44:2c:05:00:11:22",
        uuid_str: str = "123e4567-e89b-12d3-a456-426614174000",
        password: str | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
        udp_port: int = 0,
        response_udp_port: int = 33668,
        output_dir: str = "./extracted_fw",
    ) -> None:
        self.mac_address = mac_address
        self.uuid_str = uuid_str
        self.password = password
        self.host = host
        self.port = port
        self.udp_port = udp_port
        self.response_udp_port = response_udp_port
        self.output_dir = output_dir

        self.device = FakeRainbirdDevice(output_dir=output_dir)
        self.device.set_model("ESP-TM2")  # default

        self._udp_transport: asyncio.DatagramTransport | None = None
        self._http_runner: web.AppRunner | None = None
        self._http_site: web.TCPSite | None = None

    async def start(self) -> None:
        """Start both UDP discovery and HTTP stick server."""
        # 1. UDP Discovery Server
        loop = asyncio.get_running_loop()
        _LOGGER.info(
            "Starting UDP Discovery Server on %s:%d...", self.host, self.udp_port
        )

        # Set socket options for broadcast / address reuse
        try:
            self._udp_transport, _ = await loop.create_datagram_endpoint(
                lambda: RainbirdUDPDiscoveryProtocol(
                    self.mac_address, self.uuid_str, self.response_udp_port
                ),
                local_addr=(self.host, self.udp_port),
                allow_broadcast=True,
            )
        except Exception as e:
            _LOGGER.error("Failed to start UDP Discovery Server: %s", e)

        # 2. HTTP Web Server
        _LOGGER.info("Starting HTTP Stick Server on %s:%d...", self.host, self.port)
        app = web.Application()
        app["password"] = self.password
        app["device"] = self.device

        app.router.add_post("/stick", self._handle_stick)
        app.router.add_post("/stick:80", self._handle_stick)

        self._http_runner = web.AppRunner(app)
        await self._http_runner.setup()
        self._http_site = web.TCPSite(self._http_runner, self.host, self.port)
        await self._http_site.start()

    async def stop(self) -> None:
        """Stop both servers."""
        if self._udp_transport:
            self._udp_transport.close()
            self._udp_transport = None
            _LOGGER.info("Stopped UDP Discovery Server.")

        if self._http_site:
            await self._http_site.stop()
            self._http_site = None
        if self._http_runner:
            await self._http_runner.cleanup()
            self._http_runner = None
            _LOGGER.info("Stopped HTTP Stick Server.")

    @property
    def http_port(self) -> int:
        """Return the actual HTTP port the server is listening on."""
        if not self._http_runner or not self._http_runner.addresses:
            raise RuntimeError("HTTP server is not running")
        return self._http_runner.addresses[0][1]

    @property
    def host_port(self) -> str:
        """Return the host:port string of the running server."""
        return f"{self.host}:{self.http_port}"

    async def __aenter__(self) -> "RainbirdFakeServer":
        await self.start()
        return self

    async def __aexit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> None:
        await self.stop()

    async def _handle_stick(self, request: web.Request) -> web.Response:
        """Handle JSON-RPC requests sent to the stick endpoint."""
        body = await request.read()
        pwd = request.app["password"]
        device = request.app["device"]

        # Parse JSON-RPC
        decoded_request = device.process_request(body, pwd)
        if not decoded_request:
            try:
                decoded_request = json.loads(body.decode("utf-8"))
            except Exception:
                return web.Response(
                    status=400, text="Bad Request: Decryption or JSON parsing failed"
                )

        method = decoded_request.get("method")
        req_id = decoded_request.get("id", 1)

        _LOGGER.info("Handling RPC method: %s", method)

        if method == "requestFwUpdate":
            params = decoded_request.get("params", {})
            lnk_update_url = params.get("lnk_update_url")
            unv_update_url = params.get("unv_update_url")
            update_url = lnk_update_url or unv_update_url

            if update_url:
                await device.start_firmware_update(update_url)

            # Response payload for requestFwUpdate trigger success
            response_data = {
                "jsonrpc": "2.0",
                "result": {"status": "OK"},
                "id": req_id,
            }

        elif method == "getFwUpdateStatus":
            result = device.get_firmware_update_status()
            response_data = {
                "jsonrpc": "2.0",
                "result": result,
                "id": req_id,
            }

        else:
            # Handle standard SIP tunnel / command requests
            resp_bytes = device.generate_response(decoded_request, pwd)
            if resp_bytes is not None:
                return web.Response(
                    body=resp_bytes, content_type="application/octet-stream"
                )

            # Fallback for unhandled methods to prevent app crash
            response_data = {
                "jsonrpc": "2.0",
                "result": {},
                "id": req_id,
            }

        # Format and encrypt if password set
        if pwd:
            payload_bytes = encrypt(json.dumps(response_data), pwd)
            return web.Response(
                body=payload_bytes, content_type="application/octet-stream"
            )

        return web.json_response(response_data)
