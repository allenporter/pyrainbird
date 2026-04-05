"""Test fixtures for pyrainbird."""

import json
from collections.abc import Awaitable, Callable, Generator
from typing import cast
from unittest.mock import patch

import aiohttp
import pytest
from aiohttp.test_utils import TestClient

from pyrainbird import encryption
from pyrainbird.async_client import AsyncRainbirdClient, AsyncRainbirdController

from .fake_device import FakeRainbirdDevice, CapturedRequestLog

import itertools

ResponseResult = Callable[[aiohttp.web.Response], None]


PASSWORD = "password"
REQUEST = "example data"
LENGTH = len(REQUEST)

RESULT_DATA = "result-data"
RESPONSE = json.dumps(
    {
        "result": {
            "data": RESULT_DATA,
        }
    }
)
RESPONSE = encryption.encrypt(RESPONSE, PASSWORD)


@pytest.fixture(autouse=True)
def patch_request_id() -> Generator[None, None, None]:
    """Patch the request ID to be a deterministic sequence."""
    counter = itertools.count(1)
    with patch("pyrainbird.encryption.time.time", side_effect=lambda: next(counter)):
        yield


@pytest.fixture
def fake_device(app: aiohttp.web.Application) -> FakeRainbirdDevice:
    """Fixture to inject a fake device."""
    device = FakeRainbirdDevice()
    app["fake_device"] = device
    return device


@pytest.fixture
def request_log(fake_device: FakeRainbirdDevice) -> CapturedRequestLog:
    """Fixture to capture request payloads."""
    return fake_device.request_log


async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Handles the request, inserting response prepared by tests."""
    assert request.content_type == "application/octet-stream"
    body = await request.read()

    response_to_send = request.app["response"].pop(0)

    device = request.app.get("fake_device")
    decoded_request = None
    if device is not None:
        pwd = PASSWORD if request.path == "/stick" else None
        decoded_request = device.process_request(body, pwd)
        body_bytes = (
            response_to_send.body if isinstance(response_to_send.body, bytes) else None
        )
        device.process_response(body_bytes, response_to_send.status, pwd)

    request.app["request"].append(
        decoded_request if decoded_request is not None else {}
    )
    return response_to_send


@pytest.fixture(name="app")
def mock_app() -> aiohttp.web.Application:
    """Fixture to create the fake web app."""
    app = aiohttp.web.Application()
    app["response"] = []
    app["request"] = []
    app.router.add_post("/stick", handler)
    app.router.add_post("/phone-api", handler)
    return app


@pytest.fixture(name="test_client")
def cli_cb(
    app: aiohttp.web.Application,
    aiohttp_client: Callable[[aiohttp.web.Application], Awaitable[TestClient]],
) -> Callable[[], Awaitable[TestClient]]:
    """Creates a fake aiohttp client."""

    async def func() -> TestClient:
        return await aiohttp_client(app)

    return func


@pytest.fixture(name="rainbird_client")
def mock_rainbird_client(
    test_client: Callable[[], Awaitable[TestClient]],
) -> Callable[[], Awaitable[AsyncRainbirdClient]]:
    """Fixture to fake out the auth library."""

    async def func() -> AsyncRainbirdClient:
        client = await test_client()
        return AsyncRainbirdClient(
            cast(aiohttp.ClientSession, client), "/stick", PASSWORD
        )

    return func


@pytest.fixture(name="cloud_client")
def mock_cloud_client(
    test_client: Callable[[], Awaitable[TestClient]],
) -> Callable[[], Awaitable[AsyncRainbirdClient]]:
    """Fixture to fake out the auth library."""

    async def func() -> AsyncRainbirdClient:
        client = await test_client()
        return AsyncRainbirdClient(
            cast(aiohttp.ClientSession, client), "/phone-api", password=None
        )

    return func


@pytest.fixture(name="rainbird_controller")
def mock_rainbird_controller(
    rainbird_client: Callable[[], Awaitable[AsyncRainbirdClient]],
    cloud_client: Callable[[], Awaitable[AsyncRainbirdClient]],
) -> Callable[[], Awaitable[AsyncRainbirdController]]:
    """Fixture to fake out the auth library."""

    async def func() -> AsyncRainbirdController:
        local = await rainbird_client()
        cloud = await cloud_client()
        return AsyncRainbirdController(local, cloud)

    return func


@pytest.fixture(name="response")
def mock_response(app: aiohttp.web.Application) -> ResponseResult:
    """Fixture to construct a fake API response."""

    def _put_result(response: aiohttp.web.Response) -> None:
        app["response"].append(response)

    return _put_result
