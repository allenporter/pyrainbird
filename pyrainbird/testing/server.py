"""Async UDP and HTTP Server for Simulated Rain Bird Device."""

import asyncio
import json
import logging
import ssl
from typing import Self

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
        except Exception:
            _LOGGER.exception("Error in UDP discovery handler")


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
        model: str = "ESP-TM2",
        ssl_context: ssl.SSLContext | None = None,
        max_concurrent_requests: int | None = None,
        request_delay: float = 0.0,
    ) -> None:
        self.mac_address = mac_address
        self.uuid_str = uuid_str
        self.host = host
        self.port = port
        self.udp_port = udp_port
        self.response_udp_port = response_udp_port
        self.output_dir = output_dir
        self.ssl_context = ssl_context
        self.max_concurrent_requests = max_concurrent_requests
        self.request_delay = request_delay
        self._in_flight_requests = 0
        self.max_observed_concurrency = 0

        self.device = FakeRainbirdDevice(
            output_dir=output_dir,
            model=model,
            password=password,
        )

        self._udp_transport: asyncio.DatagramTransport | None = None
        self._http_runner: web.AppRunner | None = None
        self._http_site: web.TCPSite | None = None

    @property
    def password(self) -> str | None:
        """Return the current stick password."""
        return self.device.device.password

    @password.setter
    def password(self, value: str | None) -> None:
        self.device.device.password = value
        self.device.device.encryption_required = bool(value)

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
        except Exception as e:  # noqa: BLE001
            _LOGGER.error("Failed to start UDP Discovery Server: %s", e)

        # 2. HTTP Web Server
        _LOGGER.info("Starting HTTP Stick Server on %s:%d...", self.host, self.port)
        app = web.Application()
        app["device"] = self.device

        app.router.add_post("/stick", self._handle_stick)
        app.router.add_post("/stick:80", self._handle_stick)

        self._http_runner = web.AppRunner(app)
        await self._http_runner.setup()
        self._http_site = web.TCPSite(
            self._http_runner,
            self.host,
            self.port,
            ssl_context=self.ssl_context,
        )
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

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> None:
        await self.stop()

    async def _handle_stick(self, request: web.Request) -> web.Response:
        """Handle JSON-RPC requests sent to the stick endpoint."""
        self._in_flight_requests += 1
        self.max_observed_concurrency = max(
            self.max_observed_concurrency, self._in_flight_requests
        )
        try:
            if (
                self.max_concurrent_requests is not None
                and self._in_flight_requests > self.max_concurrent_requests
            ):
                if request.transport is not None:
                    request.transport.abort()
                return web.Response(status=503, text="Service Unavailable")
            if self.request_delay > 0.0:
                await asyncio.sleep(self.request_delay)
            return await self._dispatch_stick_request(request)
        finally:
            self._in_flight_requests -= 1

    async def _dispatch_stick_request(self, request: web.Request) -> web.Response:
        body = await request.read()
        device: FakeRainbirdDevice = request.app["device"]
        if device.stick.check_lockout():
            return web.Response(
                status=430, reason="Password Lockout", text="PASSWORD LOCKOUT"
            )

        pwd = device.device.password
        content_type = request.headers.get("Content-Type", "")
        if pwd:
            if "application/json" in content_type:
                return web.Response(status=400, text="Bad Request")
            decoded_request = device.process_request(body, pwd)
            if decoded_request is None:
                device.stick.record_auth_failure()
                return web.Response(
                    status=403, reason="Password", text="Invalid Password"
                )
        else:
            decoded_request = device.process_request(body, None)
            if decoded_request is None:
                return web.Response(status=400, text="Bad Request: Invalid JSON")

        method = decoded_request.get("method")
        req_id = decoded_request.get("id", 1)
        _LOGGER.info("Handling RPC method: %s", method)

        if method == "requestFwUpdate":
            params = decoded_request.get("params", {})
            update_url = params.get("lnk_update_url") or params.get("unv_update_url")
            if update_url:
                await device.start_firmware_update(update_url)
            response_data: dict[str, object] = {
                "jsonrpc": "2.0",
                "result": {"status": "OK"},
                "id": req_id,
            }
        elif method == "getFwUpdateStatus":
            response_data = {
                "jsonrpc": "2.0",
                "result": device.get_firmware_update_status(),
                "id": req_id,
            }
        else:
            resp_bytes = device.generate_response(decoded_request, pwd)
            if resp_bytes is not None:
                return web.Response(
                    body=resp_bytes, content_type="application/octet-stream"
                )
            response_data = {"jsonrpc": "2.0", "result": {}, "id": req_id}

        resp_pwd = device.device.password
        if resp_pwd:
            payload_bytes = encrypt(json.dumps(response_data), resp_pwd)
            return web.Response(
                body=payload_bytes, content_type="application/octet-stream"
            )
        return web.json_response(response_data)
