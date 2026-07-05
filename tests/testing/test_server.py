"""Tests for the fake Rain Bird server."""

import asyncio
import json
import socket
import tempfile
import pytest
import aiohttp
from aiohttp import web

from pyrainbird.testing.server import RainbirdFakeServer


@pytest.mark.asyncio
async def test_fake_server_lifecycle_and_discovery() -> None:
    """Test starting, stopping, discovering, and querying the fake server."""
    # Find a free port for the upgraded response UDP listener
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    resp_udp_port = sock.getsockname()[1]
    sock.close()

    # Create temporary directory for downloads
    with tempfile.TemporaryDirectory() as tmpdir:
        server = RainbirdFakeServer(
            response_udp_port=resp_udp_port,
            output_dir=tmpdir,
        )

        await server.start()

        try:
            # 1. Resolve actual ports
            http_port = server._http_runner.addresses[0][1]
            udp_port = server._udp_transport.get_extra_info("sockname")[1]

            # 2. Test UDP Discovery (Legacy mode)
            # Send RBD-ANDROID to UDP discovery port
            client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client_sock.settimeout(1.0)
            client_sock.sendto(b"RBD-ANDROID", ("127.0.0.1", udp_port))

            # Recv Legacy response (use executor to avoid blocking the event loop)
            loop = asyncio.get_running_loop()
            data, addr = await loop.run_in_executor(None, client_sock.recvfrom, 1024)
            assert data.decode("utf-8") == "442c05001122"
            client_sock.close()

            # 3. Test UDP Discovery (Upgraded mode)
            # Listen on the response_udp_port we specified
            resp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            resp_sock.settimeout(1.0)
            resp_sock.bind(("127.0.0.1", resp_udp_port))

            # Send discovery ping again
            client_sock2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client_sock2.sendto(b"RBD-ANDROID", ("127.0.0.1", udp_port))

            # Legacy response will be sent to client_sock2 (which we ignore),
            # but upgraded response should arrive on resp_sock
            data_upgraded, addr_upgraded = await loop.run_in_executor(
                None, resp_sock.recvfrom, 1024
            )
            assert (
                data_upgraded.decode("utf-8") == "123e4567-e89b-12d3-a456-426614174000"
            )
            resp_sock.close()
            client_sock2.close()

            # 4. Test HTTP Stick JSON-RPC POST `/stick`
            async with aiohttp.ClientSession() as session:
                url = f"http://127.0.0.1:{http_port}/stick"

                # Command: Model and Version (02)
                payload = {
                    "jsonrpc": "2.0",
                    "method": "tunnelSip",
                    "params": {"data": "02", "length": 1},
                    "id": 1,
                }
                async with session.post(url, json=payload) as resp:
                    assert resp.status == 200
                    resp_bytes = await resp.read()
                    resp_json = json.loads(resp_bytes.decode("utf-8"))
                    assert resp_json["id"] == 1
                    # 82 = response code (02 + 80), 0005 = model (ESP-TM2), 01 = major version, 03 = minor version
                    assert resp_json["result"]["data"] == "8200050103"

                # 5. Spin up a mock phone server to serve the firmware files
                mock_phone_app = web.Application()

                async def mock_release_json(request: web.Request) -> web.Response:
                    return web.json_response({"version": "2.0"})

                async def mock_filesystem_bin(request: web.Request) -> web.Response:
                    return web.Response(
                        body=b"fakebinarydata", content_type="application/octet-stream"
                    )

                mock_phone_app.router.add_get("/lnkfw/release.json", mock_release_json)
                mock_phone_app.router.add_get(
                    "/lnkfw/filesystem.bin", mock_filesystem_bin
                )

                phone_runner = web.AppRunner(mock_phone_app)
                await phone_runner.setup()
                phone_site = web.TCPSite(phone_runner, "127.0.0.1", 0)
                await phone_site.start()
                phone_port = phone_runner.addresses[0][1]

                try:
                    update_payload = {
                        "jsonrpc": "2.0",
                        "method": "requestFwUpdate",
                        "params": {
                            "lnk_update_url": f"http://127.0.0.1:{phone_port}/lnkfw/",
                            "unv_update_url": "",
                        },
                        "id": 2,
                    }
                    async with session.post(url, json=update_payload) as resp:
                        assert resp.status == 200
                        resp_json = await resp.json()
                        assert resp_json["result"]["status"] == "OK"

                    # Wait for download background task to finish
                    for _ in range(50):
                        status_payload = {
                            "jsonrpc": "2.0",
                            "method": "getFwUpdateStatus",
                            "id": 3,
                        }
                        async with session.post(
                            url, json=status_payload
                        ) as resp_status:
                            assert resp_status.status == 200
                            status_json = await resp_status.json()
                            res = status_json["result"]
                            if res["updateStatus"] == 0:  # OK
                                break
                        await asyncio.sleep(0.1)

                    # Assert status is OK and progress completed
                    assert res["updateStatus"] == 0
                    assert res["lnkProgress"] == 100
                finally:
                    await phone_site.stop()
                    await phone_runner.cleanup()

        finally:
            await server.stop()
