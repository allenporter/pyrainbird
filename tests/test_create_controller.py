from __future__ import annotations

from unittest import mock

import aiohttp
import pytest

from pyrainbird.async_client import (
    AsyncRainbirdClient,
    AsyncRainbirdController,
    create_controller,
)
from pyrainbird.data import ModelAndVersion
from pyrainbird.exceptions import RainbirdApiException, RainbirdAuthException


async def test_create_controller_tries_https_then_insecure_https_on_cert_error() -> (
    None
):
    attempts: list[tuple[str, object]] = []

    async def fake_get_model_and_version(
        self: AsyncRainbirdController,
    ) -> ModelAndVersion:
        local_client = self._local_client
        attempts.append((local_client._url, local_client._ssl_context))
        if (
            local_client._url.startswith("https://")
            and local_client._ssl_context is None
        ):
            raise RainbirdApiException(
                "Error communicating"
            ) from aiohttp.ClientConnectorCertificateError(None, Exception("cert"))
        return ModelAndVersion(0x0A, 1, 3)

    session = mock.AsyncMock(spec=aiohttp.ClientSession)
    with mock.patch.object(
        AsyncRainbirdController, "get_model_and_version", new=fake_get_model_and_version
    ):
        controller = await create_controller(session, "example.com", "password")

    assert controller._local_client._url == "https://example.com/stick"
    assert controller._local_client._ssl_context is False
    assert attempts == [
        ("https://example.com/stick", None),
        ("https://example.com/stick", False),
    ]


async def test_create_controller_explicit_https_tries_insecure_https_on_cert_error() -> (
    None
):
    attempts: list[tuple[str, object]] = []

    async def fake_get_model_and_version(
        self: AsyncRainbirdController,
    ) -> ModelAndVersion:
        local_client = self._local_client
        attempts.append((local_client._url, local_client._ssl_context))
        if (
            local_client._url.startswith("https://")
            and local_client._ssl_context is None
        ):
            raise RainbirdApiException(
                "Error communicating"
            ) from aiohttp.ClientConnectorCertificateError(None, Exception("cert"))
        return ModelAndVersion(0x0A, 1, 3)

    session = mock.AsyncMock(spec=aiohttp.ClientSession)
    with mock.patch.object(
        AsyncRainbirdController, "get_model_and_version", new=fake_get_model_and_version
    ):
        controller = await create_controller(
            session, "https://example.com/stick", "password"
        )

    assert controller._local_client._url == "https://example.com/stick"
    assert controller._local_client._ssl_context is False
    assert attempts == [
        ("https://example.com/stick", None),
        ("https://example.com/stick", False),
    ]


async def test_create_controller_explicit_https_does_not_fallback_to_http() -> None:
    attempts: list[tuple[str, object]] = []

    async def fake_get_model_and_version(
        self: AsyncRainbirdController,
    ) -> ModelAndVersion:
        local_client = self._local_client
        attempts.append((local_client._url, local_client._ssl_context))
        raise RainbirdApiException(
            "Error communicating"
        ) from aiohttp.ClientConnectorError(None, OSError("connect"))

    session = mock.AsyncMock(spec=aiohttp.ClientSession)
    with mock.patch.object(
        AsyncRainbirdController, "get_model_and_version", new=fake_get_model_and_version
    ):
        with pytest.raises(RainbirdApiException):
            await create_controller(session, "https://example.com/stick", "password")

    assert attempts == [("https://example.com/stick", None)]


async def test_create_controller_tries_https_then_http_on_connection_error() -> None:
    attempts: list[tuple[str, object]] = []

    async def fake_get_model_and_version(
        self: AsyncRainbirdController,
    ) -> ModelAndVersion:
        local_client = self._local_client
        attempts.append((local_client._url, local_client._ssl_context))
        if local_client._url.startswith("https://"):
            raise RainbirdApiException(
                "Error communicating"
            ) from aiohttp.ClientConnectorError(None, OSError("connect"))
        return ModelAndVersion(0x0A, 1, 3)

    session = mock.AsyncMock(spec=aiohttp.ClientSession)
    with mock.patch.object(
        AsyncRainbirdController, "get_model_and_version", new=fake_get_model_and_version
    ):
        controller = await create_controller(session, "example.com", "password")

    assert controller._local_client._url == "http://example.com/stick"
    assert controller._local_client._ssl_context is None
    assert attempts == [
        ("https://example.com/stick", None),
        ("http://example.com/stick", None),
    ]


async def test_create_controller_does_not_fallback_on_auth_error() -> None:
    async def fake_get_model_and_version(
        self: AsyncRainbirdController,
    ) -> ModelAndVersion:
        raise RainbirdAuthException("bad password")

    session = mock.AsyncMock(spec=aiohttp.ClientSession)
    with mock.patch.object(
        AsyncRainbirdController, "get_model_and_version", new=fake_get_model_and_version
    ):
        with pytest.raises(RainbirdAuthException):
            await create_controller(session, "example.com", "password")


async def test_create_controller_skips_discovery_for_path_host() -> None:
    session = mock.AsyncMock(spec=aiohttp.ClientSession)
    controller = await create_controller(session, "/stick", "password")
    assert controller._local_client._url == "/stick"


async def test_rainbird_client_only_passes_ssl_kwarg_when_configured() -> None:
    session = mock.AsyncMock(spec=aiohttp.ClientSession)

    response = mock.Mock()
    response.raise_for_status = mock.Mock()
    response.read = mock.AsyncMock(return_value=b"raw")

    session.request = mock.AsyncMock(return_value=response)

    client = AsyncRainbirdClient(session, "example.com", "password", scheme="https")
    client._coder = mock.Mock()
    client._coder.encode_command.return_value = b"payload"
    client._coder.decode_command.return_value = {}

    await client.request("getModelAndVersion")
    _, request_kwargs = session.request.call_args
    assert "ssl" not in request_kwargs

    session.request.reset_mock()

    insecure_client = AsyncRainbirdClient(
        session, "example.com", "password", scheme="https", ssl_context=False
    )
    insecure_client._coder = mock.Mock()
    insecure_client._coder.encode_command.return_value = b"payload"
    insecure_client._coder.decode_command.return_value = {}

    await insecure_client.request("getModelAndVersion")
    _, request_kwargs = session.request.call_args
    assert request_kwargs["ssl"] is False
