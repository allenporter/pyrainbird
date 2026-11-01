"""Tests for the fake Rain Bird server."""

import asyncio
import datetime
import json
import socket
import ssl
import tempfile

import aiohttp
import pytest
from aiohttp import web
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from pyrainbird.encryption import decrypt, encrypt
from pyrainbird.testing.server import RainbirdFakeServer


def create_self_signed_ssl_context() -> ssl.SSLContext:
    """Create an ephemeral self-signed EC P-256 server SSLContext for local HTTPS testing."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    with (
        tempfile.NamedTemporaryFile(suffix=".pem") as cert_file,
        tempfile.NamedTemporaryFile(suffix=".pem") as key_file,
    ):
        cert_file.write(cert.public_bytes(serialization.Encoding.PEM))
        cert_file.flush()
        key_file.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
        key_file.flush()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=cert_file.name, keyfile=key_file.name)
    return ctx


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
            data, _addr = await loop.run_in_executor(None, client_sock.recvfrom, 1024)
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
            data_upgraded, _addr_upgraded = await loop.run_in_executor(
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


@pytest.mark.asyncio
async def test_fake_server_auth_failure_and_430_lockout() -> None:
    """Verify RainbirdFakeServer returns 403 on bad password and 430 once locked out."""
    async with (
        RainbirdFakeServer(password="123456", model="ARC8") as server,
        aiohttp.ClientSession() as session,
    ):
        server.device.device.lockout_tries = 2
        url = f"http://{server.host_port}/stick"
        rpc_body = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "tunnelSip",
                "params": {"data": "02", "length": 1},
                "id": 1,
            }
        )

        # Plaintext application/json is rejected with 400 without burning lockout tries
        async with session.post(url, json=json.loads(rpc_body)) as resp_400:
            assert resp_400.status == 400
        assert server.device.device.failed_attempts == 0

        bad_payload = encrypt(rpc_body, "wrong-pin")
        headers = {"Content-Type": "application/octet-stream"}

        async with session.post(url, data=bad_payload, headers=headers) as resp_1:
            assert resp_1.status == 403
            assert await resp_1.text() == "Invalid Password"

        async with session.post(url, data=bad_payload, headers=headers) as resp_2:
            assert resp_2.status == 403

        good_payload = encrypt(rpc_body, "123456")
        async with session.post(
            url, data=good_payload, headers=headers
        ) as resp_lockout:
            assert resp_lockout.status == 430
            assert await resp_lockout.text() == "PASSWORD LOCKOUT"


@pytest.mark.asyncio
@pytest.mark.parametrize("empty_pwd", [None, ""])
async def test_fake_server_empty_password_octet_stream(empty_pwd: str | None) -> None:
    """Verify RainbirdFakeServer supports unencrypted /stick over application/octet-stream."""
    async with (
        RainbirdFakeServer(password=empty_pwd, model="ARC8") as server,
        aiohttp.ClientSession() as session,
    ):
        url = f"http://{server.host_port}/stick"
        rpc_body = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "tunnelSip",
                "params": {"data": "02", "length": 1},
                "id": 1,
            }
        )
        headers = {"Content-Type": "application/octet-stream"}

        async with session.post(
            url, data=rpc_body.encode("utf-8"), headers=headers
        ) as resp_ok:
            assert resp_ok.status == 200
            resp_json = json.loads((await resp_ok.read()).decode("utf-8"))
            assert resp_json["result"]["data"] == "8208130103"

        async with session.post(
            url, data=encrypt(rpc_body, "123456"), headers=headers
        ) as resp_bad:
            assert resp_bad.status == 400


@pytest.mark.asyncio
async def test_fake_server_https_and_single_socket_concurrency() -> None:
    """Verify RainbirdFakeServer serves self-signed HTTPS and enforces max_concurrent_requests=1."""
    ssl_ctx = create_self_signed_ssl_context()
    async with (
        RainbirdFakeServer(
            password="123456",
            model="ARC8",
            ssl_context=ssl_ctx,
            max_concurrent_requests=1,
            request_delay=0.05,
        ) as server,
        aiohttp.ClientSession() as session,
    ):
        url = f"https://{server.host_port}/stick"
        rpc_body = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "tunnelSip",
                "params": {"data": "02", "length": 1},
                "id": 1,
            }
        )
        payload = encrypt(rpc_body, "123456")
        headers = {"Content-Type": "application/octet-stream"}

        async with session.post(
            url, data=payload, headers=headers, ssl=False
        ) as resp_ok:
            assert resp_ok.status == 200
            decrypted = decrypt(await resp_ok.read(), "123456").rstrip(b"\x10\x0a\x00 ")
            assert (
                json.loads(decrypted.decode("utf-8"))["result"]["data"] == "8208130103"
            )

        with pytest.raises(aiohttp.ClientConnectionError):
            await asyncio.gather(
                session.post(url, data=payload, headers=headers, ssl=False),
                session.post(url, data=payload, headers=headers, ssl=False),
            )
        assert server.max_observed_concurrency == 2
