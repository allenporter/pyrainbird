"""Unit tests for the Rainbird cloud WebSocket stream client."""

import asyncio
import base64
import datetime
import json
from collections.abc import Generator
from unittest import mock

import aiohttp
import pytest
from aiohttp.test_utils import TestClient

from pyrainbird.async_client import RainbirdTokenProvider
from pyrainbird.cloud.stream import AsyncRainbirdCloudStream
from pyrainbird.exceptions import RainbirdAuthException


class MockTokenProvider(RainbirdTokenProvider):
    """Mock token provider that tracks refresh calls."""

    def __init__(self, token: str = "initial_token") -> None:
        self.token = token
        self.calls = 0

    async def async_get_token(self, force_refresh: bool = False) -> str:
        self.calls += 1
        if force_refresh:
            self.token = f"refreshed_token_{self.calls}"
        return self.token


@pytest.fixture
def mock_ws_app() -> aiohttp.web.Application:
    """Fixture to set up a mock WebSocket server application."""
    app = aiohttp.web.Application()
    app["behavior"] = "success"  # "success", "auth_error", "disconnect", "sub_error"
    app["connection_count"] = 0
    app["messages_received"] = []

    async def ws_handler(request: aiohttp.web.Request) -> aiohttp.web.WebSocketResponse:
        app["connection_count"] += 1
        ws = aiohttp.web.WebSocketResponse()
        await ws.prepare(request)

        # Retrieve authorization from request header parameter
        header_param = request.query.get("header", "")
        token_str = ""
        if header_param:
            try:
                # Add back padding if needed
                padded = header_param + "=" * ((4 - len(header_param) % 4) % 4)
                header_data = json.loads(
                    base64.urlsafe_b64decode(padded).decode("utf-8")
                )
                token_str = header_data.get("Authorization", "")
            except Exception:
                pass

        if app["behavior"] == "auth_error" and "refreshed_token" not in token_str:
            # Send connection_error to simulate auth failure for non-refreshed tokens
            await ws.send_json(
                {
                    "type": "connection_error",
                    "payload": {
                        "errors": [
                            {
                                "errorType": "UnauthorizedException",
                                "message": "Token expired or invalid",
                            }
                        ]
                    },
                }
            )
            await ws.close()
            return ws

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = msg.json()
                app["messages_received"].append(data)
                msg_type = data.get("type")

                if msg_type == "connection_init":
                    await ws.send_json({"type": "connection_ack"})

                elif msg_type == "start":
                    if app["behavior"] == "sub_error":
                        await ws.send_json(
                            {
                                "type": "error",
                                "id": "sub_device_state",
                                "payload": {
                                    "errors": [
                                        {"message": "Subscription validation failed"}
                                    ]
                                },
                            }
                        )
                        await ws.close()
                        break

                    # Send a keep-alive
                    await ws.send_json({"type": "ka"})

                    # Send test data updates
                    await ws.send_json(
                        {
                            "id": "sub_device_state",
                            "type": "data",
                            "payload": {
                                "data": {
                                    "onUpdateDeviceStateTable": {
                                        "PK": "7b1ad1ef-91df-4e50-9004-269c139c681c",
                                        "SK": "Connected",
                                        "Data": '{"activeStation":2,"remainSec":300,"rainDelay":1}',
                                        "TimeStamp": 1781392680,
                                    }
                                }
                            },
                        }
                    )

                    # If we want to simulate disconnect immediately
                    if app["behavior"] == "disconnect":
                        await ws.close()
                        break

                    # Yield second event for success scenario
                    if app["behavior"] == "success":
                        await ws.send_json(
                            {
                                "id": "sub_device_state",
                                "type": "data",
                                "payload": {
                                    "data": {
                                        "onUpdateDeviceStateTable": {
                                            "PK": "7b1ad1ef-91df-4e50-9004-269c139c681c",
                                            "SK": "Connected",
                                            "Data": '{"activeStation":null,"remainSec":0,"rainDelay":0}',
                                            "TimeStamp": 1781392740,
                                        }
                                    }
                                },
                            }
                        )

        return ws

    app.router.add_get("/graphql", ws_handler)
    return app


def test_handshake_url_construction() -> None:
    """Test that connection URL construction builds correct base64 parameters."""
    token_provider = MockTokenProvider("test_token_xyz")
    # We pass None/mock for session since we only call the URL helper method
    stream = AsyncRainbirdCloudStream(
        token_provider, 527302, "7b1ad1ef-91df-4e50-9004-269c139c681c", None
    )  # type: ignore
    url = stream._get_connection_url("test_token_xyz")

    assert url.startswith(
        "wss://m3iuhu3l3zbjpkctbnh2of4chm.appsync-realtime-api.us-west-2.amazonaws.com/graphql?"
    )
    assert "payload=e30=" in url
    assert "header=" in url

    # Parse out and verify header parameter
    import urllib.parse

    parsed_url = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed_url.query)
    header_val = params["header"][0]
    padded = header_val + "=" * ((4 - len(header_val) % 4) % 4)
    decoded_header = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))

    assert (
        decoded_header["host"]
        == "m3iuhu3l3zbjpkctbnh2of4chm.appsync-api.us-west-2.amazonaws.com"
    )
    assert decoded_header["Authorization"] == "test_token_xyz"


@pytest.mark.asyncio
async def test_stream_success(
    mock_ws_app: aiohttp.web.Application, aiohttp_client: Generator
) -> None:
    """Test successful streaming connection, subscription, and parsing."""
    client: TestClient = await aiohttp_client(mock_ws_app)
    token_provider = MockTokenProvider("valid_token")

    # Override endpoint for test client session
    with mock.patch(
        "pyrainbird.cloud.stream.WS_ENDPOINT",
        f"ws://{client.host}:{client.port}/graphql",
    ):
        stream = AsyncRainbirdCloudStream(
            token_provider,
            527302,
            "7b1ad1ef-91df-4e50-9004-269c139c681c",
            client.session,
        )
        events = []

        async def read_stream():
            async for event in stream.listen():
                events.append(event)
                if len(events) == 2:
                    break

        await asyncio.wait_for(read_stream(), timeout=5.0)

        assert len(events) == 2

        # Verify first event
        ev1 = events[0]
        assert ev1.satellite_id == 527302
        assert ev1.device_uuid == "7b1ad1ef-91df-4e50-9004-269c139c681c"
        assert ev1.state == "Connected"
        assert ev1.active_station == 2
        assert ev1.remain_seconds == 300
        assert ev1.rain_delay == 1
        assert ev1.updated_at == datetime.datetime(
            2026, 6, 13, 23, 18, tzinfo=datetime.timezone.utc
        )

        # Verify second event
        ev2 = events[1]
        assert ev2.device_uuid == "7b1ad1ef-91df-4e50-9004-269c139c681c"
        assert ev2.active_station is None
        assert ev2.remain_seconds == 0
        assert ev2.rain_delay == 0


@pytest.mark.asyncio
async def test_stream_auth_error_refresh(
    mock_ws_app: aiohttp.web.Application, aiohttp_client: Generator
) -> None:
    """Test that auth errors force a token refresh and retry."""
    mock_ws_app["behavior"] = "auth_error"
    client: TestClient = await aiohttp_client(mock_ws_app)
    token_provider = MockTokenProvider("expired_token")

    # Override WS_ENDPOINT to connect to local mock server
    with (
        mock.patch(
            "pyrainbird.cloud.stream.WS_ENDPOINT",
            f"ws://{client.host}:{client.port}/graphql",
        ),
        mock.patch("asyncio.sleep", return_value=None),
    ):
        stream = AsyncRainbirdCloudStream(
            token_provider,
            527302,
            "7b1ad1ef-91df-4e50-9004-269c139c681c",
            client.session,
        )
        events = []

        async def read_stream():
            async for event in stream.listen():
                events.append(event)
                break

        # First connection fails because expired_token is used and handler returns auth_error.
        # This causes client to raise RainbirdAuthException and force token refresh on next retry.
        # Second connection succeeds because token provider yields a refreshed token containing "refreshed_token".
        await asyncio.wait_for(read_stream(), timeout=5.0)

        assert len(events) == 1
        assert mock_ws_app["connection_count"] == 2
        assert token_provider.calls >= 2
        assert "refreshed_token" in token_provider.token


@pytest.mark.asyncio
async def test_stream_reconnect_on_disconnect(
    mock_ws_app: aiohttp.web.Application, aiohttp_client: Generator
) -> None:
    """Test that client reconnects when connection drops."""
    mock_ws_app["behavior"] = "disconnect"
    client: TestClient = await aiohttp_client(mock_ws_app)
    token_provider = MockTokenProvider("valid_token")

    with (
        mock.patch(
            "pyrainbird.cloud.stream.WS_ENDPOINT",
            f"ws://{client.host}:{client.port}/graphql",
        ),
        mock.patch("asyncio.sleep", return_value=None),
    ):
        stream = AsyncRainbirdCloudStream(
            token_provider,
            527302,
            "7b1ad1ef-91df-4e50-9004-269c139c681c",
            client.session,
        )
        events = []

        async def read_stream():
            async for event in stream.listen():
                events.append(event)
                if len(events) == 2:
                    break

        await asyncio.wait_for(read_stream(), timeout=5.0)

        assert len(events) == 2
        assert mock_ws_app["connection_count"] >= 2


@pytest.mark.asyncio
async def test_stream_sub_error_raise(
    mock_ws_app: aiohttp.web.Application, aiohttp_client: Generator
) -> None:
    """Test that a subscription validation error raises a RainbirdAuthException."""
    mock_ws_app["behavior"] = "sub_error"
    client: TestClient = await aiohttp_client(mock_ws_app)
    token_provider = MockTokenProvider("valid_token")

    with (
        mock.patch(
            "pyrainbird.cloud.stream.WS_ENDPOINT",
            f"ws://{client.host}:{client.port}/graphql",
        ),
        mock.patch("asyncio.sleep", return_value=None),
    ):
        stream = AsyncRainbirdCloudStream(
            token_provider,
            527302,
            "7b1ad1ef-91df-4e50-9004-269c139c681c",
            client.session,
        )

        with pytest.raises(
            RainbirdAuthException, match="Subscription validation failed"
        ):
            async for _ in stream.listen():
                pass


def test_parse_event_scalar_data() -> None:
    """Test that event parsing handles scalar/non-dict 'Data' payloads without crashing."""
    token_provider = MockTokenProvider("test_token")
    stream = AsyncRainbirdCloudStream(
        token_provider, 527302, "7b1ad1ef-91df-4e50-9004-269c139c681c", None
    )  # type: ignore

    # Test case 1: Data is an integer
    event_data_int = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": "7b1ad1ef-91df-4e50-9004-269c139c681c",
                    "SK": "Connected",
                    "Data": "0",
                    "TimeStamp": 1781392680,
                }
            }
        }
    }
    event = stream._parse_event(event_data_int)
    assert event is not None
    assert event.state == "0"
    assert event.active_station is None
    assert event.remain_seconds is None

    # Test case 2: Data is a string representing a non-dict value
    event_data_str = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": "7b1ad1ef-91df-4e50-9004-269c139c681c",
                    "SK": "Connected",
                    "Data": '"offline"',
                    "TimeStamp": 1781392680,
                }
            }
        }
    }
    event = stream._parse_event(event_data_str)
    assert event is not None
    assert event.state == "offline"
