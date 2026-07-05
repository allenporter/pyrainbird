"""Unit tests for the Rainbird cloud WebSocket stream client."""

import asyncio
import base64
import datetime
import glob
import json
import pathlib
from collections.abc import Generator
from typing import Any
from unittest import mock

import aiohttp
import pytest
from aiohttp.test_utils import TestClient

from pyrainbird.async_client import RainbirdTokenProvider
from pyrainbird.cloud import (
    AsyncRainbirdCloudStream,
    ConnectionStatusEvent,
    GenericCloudStreamEvent,
    RainSensorStateEvent,
    RssiStateEvent,
    StationStateEvent,
)
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

                    if app["behavior"] == "invalid_json":
                        await ws.send_str("{invalid_json_here")
                        await ws.close()
                        break

                    if app["behavior"] == "complete":
                        await ws.send_json({"type": "complete"})
                        await ws.close()
                        break

                    if app["behavior"] == "server_error":
                        await ws.send_json(
                            {
                                "type": "error",
                                "id": "sub_device_state",
                                "payload": {
                                    "errors": [{"message": "Generic server error"}]
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
        assert isinstance(ev1, ConnectionStatusEvent)
        assert ev1.satellite_id == 527302
        assert ev1.device_uuid == "7b1ad1ef-91df-4e50-9004-269c139c681c"
        assert ev1.is_connected is True
        assert ev1.active_station == 2
        assert ev1.remaining_seconds == 300
        assert ev1.rain_delay == 1
        assert ev1.updated_at == datetime.datetime(
            2026, 6, 13, 23, 18, tzinfo=datetime.timezone.utc
        )

        # Verify second event
        ev2 = events[1]
        assert isinstance(ev2, ConnectionStatusEvent)
        assert ev2.device_uuid == "7b1ad1ef-91df-4e50-9004-269c139c681c"
        assert ev2.is_connected is True
        assert ev2.active_station is None
        assert ev2.remaining_seconds == 0
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


TEST_DATA_DIR = pathlib.Path(__file__).parent / "testdata"
JSON_FILES = sorted(glob.glob(str(TEST_DATA_DIR / "*.json")))
JSON_IDS = [pathlib.Path(f).stem for f in JSON_FILES]


@pytest.mark.parametrize(
    "json_path",
    JSON_FILES,
    ids=JSON_IDS,
)
def test_parse_event_snapshot(json_path: str, snapshot: Any) -> None:
    """Test parsing of a cloud stream event JSON file against a syrupy snapshot."""
    token_provider = MockTokenProvider("test_token")
    stream = AsyncRainbirdCloudStream(
        token_provider, 527302, "7b1ad1ef-91df-4e50-9004-269c139c681c", None
    )  # type: ignore

    with open(json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    event = stream._parse_event(payload)
    assert event is not None

    assert event == snapshot


def test_parse_event_rssi() -> None:
    """Test that _parse_event correctly parses RSSI status events."""
    stream = AsyncRainbirdCloudStream(
        MockTokenProvider(), 527302, "7b1ad1ef-91df-4e50-9004-269c139c681c", None
    )  # type: ignore

    rssi_raw = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": "7b1ad1ef-91df-4e50-9004-269c139c681c",
                    "SK": "RSSI",
                    "Data": "-82",
                    "TimeStamp": 1781392680,
                }
            }
        }
    }
    ev = stream._parse_event(rssi_raw)
    assert isinstance(ev, RssiStateEvent)
    assert ev.rssi == -82


def test_parse_event_rain_sensor_wet() -> None:
    """Test that _parse_event parses wet RainSensorState events."""
    stream = AsyncRainbirdCloudStream(
        MockTokenProvider(), 527302, "7b1ad1ef-91df-4e50-9004-269c139c681c", None
    )  # type: ignore

    sensor_wet_raw = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": "7b1ad1ef-91df-4e50-9004-269c139c681c",
                    "SK": "Event#RainSensorState",
                    "Data": '{"state":1}',
                    "TimeStamp": 1781392680,
                }
            }
        }
    }
    ev = stream._parse_event(sensor_wet_raw)
    assert isinstance(ev, RainSensorStateEvent)
    assert ev.is_wet is True


def test_parse_event_rain_sensor_dry() -> None:
    """Test that _parse_event parses dry RainSensorState events."""
    stream = AsyncRainbirdCloudStream(
        MockTokenProvider(), 527302, "7b1ad1ef-91df-4e50-9004-269c139c681c", None
    )  # type: ignore

    sensor_dry_raw = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": "7b1ad1ef-91df-4e50-9004-269c139c681c",
                    "SK": "Event#RainSensorState",
                    "Data": '{"state":0}',
                    "TimeStamp": 1781392680,
                }
            }
        }
    }
    ev = stream._parse_event(sensor_dry_raw)
    assert isinstance(ev, RainSensorStateEvent)
    assert ev.is_wet is False


def test_parse_event_station_watering() -> None:
    """Test that _parse_event parses active watering StationState events."""
    stream = AsyncRainbirdCloudStream(
        MockTokenProvider(), 527302, "7b1ad1ef-91df-4e50-9004-269c139c681c", None
    )  # type: ignore

    station_on_raw = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": "7b1ad1ef-91df-4e50-9004-269c139c681c",
                    "SK": "Station3",
                    "Data": '{"state":1,"remainSec":1781393280,"programNumber":36}',
                    "TimeStamp": 1781392680,
                }
            }
        }
    }
    ev = stream._parse_event(station_on_raw)
    assert isinstance(ev, StationStateEvent)
    assert ev.zone == 3
    assert ev.is_watering is True
    assert ev.remaining_seconds == 600
    assert ev.program_number == 36


def test_parse_event_station_stopped() -> None:
    """Test that _parse_event parses stopped/idle StationState events."""
    stream = AsyncRainbirdCloudStream(
        MockTokenProvider(), 527302, "7b1ad1ef-91df-4e50-9004-269c139c681c", None
    )  # type: ignore

    station_off_raw = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": "7b1ad1ef-91df-4e50-9004-269c139c681c",
                    "SK": "Station3",
                    "Data": '{"state":-1,"remainSec":0,"programNumber":36}',
                    "TimeStamp": 1781392680,
                }
            }
        }
    }
    ev = stream._parse_event(station_off_raw)
    assert isinstance(ev, StationStateEvent)
    assert ev.zone == 3
    assert ev.is_watering is False
    assert ev.remaining_seconds == 0
    assert ev.program_number == 36


def test_parse_event_generic() -> None:
    """Test that _parse_event parses other unknown database table records into GenericCloudStreamEvent."""
    stream = AsyncRainbirdCloudStream(
        MockTokenProvider(), 527302, "7b1ad1ef-91df-4e50-9004-269c139c681c", None
    )  # type: ignore

    generic_raw = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": "7b1ad1ef-91df-4e50-9004-269c139c681c",
                    "SK": "UnknownKey",
                    "Data": '{"foo":"bar"}',
                    "TimeStamp": 1781392680,
                }
            }
        }
    }
    ev = stream._parse_event(generic_raw)
    assert isinstance(ev, GenericCloudStreamEvent)
    assert ev.event_key == "UnknownKey"
    assert ev.raw_data == '{"foo":"bar"}'


def test_parse_event_invalid_payloads() -> None:
    """Test that _parse_event safely returns None for invalid or incomplete payloads."""
    stream = AsyncRainbirdCloudStream(
        MockTokenProvider(), 527302, "7b1ad1ef-91df-4e50-9004-269c139c681c", None
    )  # type: ignore

    assert stream._parse_event("not_a_dict") is None
    assert stream._parse_event({}) is None
    assert stream._parse_event({"payload": {}}) is None

    bad_record = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": {},
                    "SK": "Station1",
                    "Data": "some_data",
                }
            }
        }
    }
    assert stream._parse_event(bad_record) is None

    rssi_no_data = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": "uuid",
                    "SK": "RSSI",
                    "Data": None,
                    "TimeStamp": 100,
                }
            }
        }
    }
    assert stream._parse_event(rssi_no_data) is None

    rssi_bad_data = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": "uuid",
                    "SK": "RSSI",
                    "Data": "not_an_int",
                    "TimeStamp": 100,
                }
            }
        }
    }
    assert stream._parse_event(rssi_bad_data) is None

    rain_no_data = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": "uuid",
                    "SK": "Event#RainSensorState",
                    "Data": None,
                    "TimeStamp": 100,
                }
            }
        }
    }
    assert stream._parse_event(rain_no_data) is None

    rain_bad_data = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": "uuid",
                    "SK": "Event#RainSensorState",
                    "Data": "not_json{",
                    "TimeStamp": 100,
                }
            }
        }
    }
    assert stream._parse_event(rain_bad_data) is None

    station_bad_suffix = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": "uuid",
                    "SK": "StationABC",
                    "Data": '{"state": 1}',
                    "TimeStamp": 100,
                }
            }
        }
    }
    assert stream._parse_event(station_bad_suffix) is None

    station_no_data = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": "uuid",
                    "SK": "Station1",
                    "Data": None,
                    "TimeStamp": 100,
                }
            }
        }
    }
    assert stream._parse_event(station_no_data) is None

    station_bad_parse = {
        "payload": {
            "data": {
                "onUpdateDeviceStateTable": {
                    "PK": "uuid",
                    "SK": "Station1",
                    "Data": "{bad_json",
                    "TimeStamp": 100,
                }
            }
        }
    }
    assert stream._parse_event(station_bad_parse) is None


@pytest.mark.asyncio
async def test_stream_token_retrieval_failure() -> None:
    """Test that stream.listen() raises RainbirdAuthException when token acquisition fails."""
    token_provider = mock.MagicMock(spec=RainbirdTokenProvider)
    token_provider.async_get_token = mock.AsyncMock(
        side_effect=RainbirdAuthException("Token fetch failed")
    )

    stream = AsyncRainbirdCloudStream(
        token_provider, 527302, "7b1ad1ef-91df-4e50-9004-269c139c681c", mock.MagicMock()
    )  # type: ignore

    with pytest.raises(RainbirdAuthException, match="Token acquisition failed"):
        async for _ in stream.listen():
            pass


@pytest.mark.asyncio
async def test_stream_websocket_json_parse_error(
    mock_ws_app: aiohttp.web.Application, aiohttp_client: Generator
) -> None:
    """Test stream does not crash and continues reading when it receives non-JSON WebSocket messages."""
    mock_ws_app["behavior"] = "invalid_json"
    client: TestClient = await aiohttp_client(mock_ws_app)
    token_provider = MockTokenProvider("test_token")

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
        )  # type: ignore

        events = []

        async def consume():
            async for event in stream.listen():
                events.append(event)

        await asyncio.wait_for(consume(), timeout=0.5)
        assert len(events) == 0


@pytest.mark.asyncio
async def test_stream_websocket_close_frames(
    mock_ws_app: aiohttp.web.Application, aiohttp_client: Generator
) -> None:
    """Test that the stream exits reading loop cleanly when receiving socket close messages."""
    mock_ws_app["behavior"] = "complete"
    client: TestClient = await aiohttp_client(mock_ws_app)
    token_provider = MockTokenProvider("test_token")

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
        )  # type: ignore

        events = []

        async def consume():
            async for event in stream.listen():
                events.append(event)

        await asyncio.wait_for(consume(), timeout=0.5)
        assert len(events) == 0


@pytest.mark.asyncio
async def test_stream_websocket_cancelled() -> None:
    """Test that stream listener cleans up and closes websocket when task is cancelled."""
    token_provider = MockTokenProvider("test_token")
    mock_ws = mock.AsyncMock()
    mock_ws.closed = False
    mock_ws.close = mock.AsyncMock()

    mock_client = mock.MagicMock(spec=aiohttp.ClientSession)
    mock_client.ws_connect = mock.MagicMock()
    mock_cm = mock.AsyncMock()
    mock_cm.__aenter__ = mock.AsyncMock(return_value=mock_ws)
    mock_cm.__aexit__ = mock.AsyncMock(return_value=None)
    mock_client.ws_connect.return_value = mock_cm

    stream = AsyncRainbirdCloudStream(
        token_provider, 527302, "7b1ad1ef-91df-4e50-9004-269c139c681c", mock_client
    )  # type: ignore

    async def mock_iter(*args: Any, **kwargs: Any) -> Any:
        raise asyncio.CancelledError()
        yield

    mock_ws.__aiter__ = mock_iter

    async for _ in stream.listen():
        pass

    mock_ws.close.assert_called_once()


@pytest.mark.asyncio
async def test_stream_auth_error_refresh_forced(
    mock_ws_app: aiohttp.web.Application, aiohttp_client: Generator
) -> None:
    """Test that stream forces token refresh when receiving authentication errors from AppSync."""
    mock_ws_app["behavior"] = "server_error"
    client: TestClient = await aiohttp_client(mock_ws_app)
    token_provider = MockTokenProvider("test_token")

    with mock.patch(
        "pyrainbird.cloud.stream.WS_ENDPOINT",
        f"ws://{client.host}:{client.port}/graphql",
    ):
        stream = AsyncRainbirdCloudStream(
            token_provider,
            527302,
            "7b1ad1ef-91df-4e50-9004-269c139c681c",
            client.session,
        )  # type: ignore

        with pytest.raises(
            RainbirdAuthException,
            match="WebSocket protocol error: Generic server error",
        ):
            async for _ in stream.listen():
                pass


@pytest.mark.asyncio
async def test_stream_connection_error_retry_backoff() -> None:
    """Test that stream retries and applies backoff when receiving ClientError, TimeoutError, or OSError."""
    token_provider = MockTokenProvider("test_token")
    mock_client = mock.MagicMock(spec=aiohttp.ClientSession)

    err = aiohttp.ClientResponseError(
        request_info=mock.Mock(), history=(), status=401, message="Unauthorized"
    )
    mock_client.ws_connect = mock.MagicMock(side_effect=[err, asyncio.CancelledError()])

    stream = AsyncRainbirdCloudStream(
        token_provider, 527302, "7b1ad1ef-91df-4e50-9004-269c139c681c", mock_client
    )  # type: ignore

    with mock.patch("asyncio.sleep", return_value=None) as mock_sleep:
        async for _ in stream.listen():
            pass

    assert token_provider.calls == 2
    assert "refreshed_token" in token_provider.token
    mock_sleep.assert_called_once()
