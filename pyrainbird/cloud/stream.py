"""Real-time cloud updates stream client using AWS AppSync GraphQL subscriptions over WebSockets.

This module implements the persistent WebSocket streaming protocol used by the newer 2.0 cloud protocol
to receive real-time controller updates (such as active station, remaining watering seconds, and
rain delay) from the AWS AppSync service without polling.

Protocol Overview:
1. Handshake URL Construction:
   AppSync requires the OIDC Authorization token and API host to be passed during the initial
   HTTP Upgrade request. These parameters must be URL-safe base64-encoded JSON strings passed
   as query parameters:
     - `header`: Contains `host` (GraphQL API host) and `Authorization` (raw OIDC JWT access token).
     - `payload`: Contains an empty JSON object `{}` (encoded as `e30=`).

2. Protocol Handshake:
   Upon opening the connection, the client sends a `connection_init` message. The server
   replies with a `connection_ack` containing connection keep-alive timeout configuration.

3. Subscription Registration:
   Once the connection is established, the client starts the subscription by sending a `start`
   type message. The subscription query is:
     subscription onUpdateDeviceStateTable($PK : String!) {
       onUpdateDeviceStateTable(PK: $PK) {
         PK
         SK
         Data
         TimeStamp
       }
     }
   - `PK` represents the Partition Key (the satellite's `device_uuid`).
   - `SK` represents the Sort Key (indicating the type of status/update).

4. Message Handling:
   - `ka`: Keep-alive message sent periodically by the server to maintain the connection.
   - `data`: Pushed event update payload. The nested `Data` field contains a JSON-serialized
     string detailing the active station status:
       {"activeStation": <int|null>, "remainSec": <int>, "rainDelay": <int>}
"""

import asyncio
import base64
import datetime
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import aiohttp

from pyrainbird.async_client import RainbirdTokenProvider
from pyrainbird.exceptions import RainbirdAuthException

_LOGGER = logging.getLogger(__name__)

API_HOST = "m3iuhu3l3zbjpkctbnh2of4chm.appsync-api.us-west-2.amazonaws.com"
REALTIME_HOST = (
    "m3iuhu3l3zbjpkctbnh2of4chm.appsync-realtime-api.us-west-2.amazonaws.com"
)
WS_ENDPOINT = f"wss://{REALTIME_HOST}/graphql"

# Reconnection backoff parameters
INITIAL_BACKOFF = 2.0
MAX_BACKOFF = 60.0
BACKOFF_FACTOR = 2.0


@dataclass
class CloudStreamEvent:
    """Base class for real-time cloud satellite events."""

    satellite_id: int
    device_uuid: str
    updated_at: datetime.datetime


@dataclass
class StationStateEvent(CloudStreamEvent):
    """Fired when a specific zone/station starts or stops watering."""

    zone: int
    is_watering: bool
    remaining_seconds: int | None
    program_number: int | None


@dataclass
class RainSensorStateEvent(CloudStreamEvent):
    """Fired when the rain sensor detects wet/dry status changes."""

    is_wet: bool


@dataclass
class ConnectionStatusEvent(CloudStreamEvent):
    """Fired with overall connection and active status details."""

    is_connected: bool
    active_station: int | None
    remaining_seconds: int | None
    rain_delay: int | None


@dataclass
class RssiStateEvent(CloudStreamEvent):
    """Fired when device RSSI (signal strength) changes."""

    rssi: int


@dataclass
class GenericCloudStreamEvent(CloudStreamEvent):
    """Catch-all event for any unknown/new sort keys (future-proofing)."""

    event_key: str
    raw_data: str | None


class AsyncRainbirdCloudStream:
    """Manages a real-time WebSocket subscription stream to AWS AppSync."""

    def __init__(
        self,
        token_provider: RainbirdTokenProvider,
        satellite_id: int,
        device_uuid: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the real-time cloud stream manager."""
        self._token_provider = token_provider
        self._satellite_id = satellite_id
        self._device_uuid = device_uuid
        self._session = session
        self._force_refresh_token = False

    def _get_connection_url(self, token: str) -> str:
        """Construct the authenticated AppSync WebSocket handshake URL."""
        headers = {
            "host": API_HOST,
            "Authorization": token,
        }
        headers_json = json.dumps(headers).encode("utf-8")
        headers_b64 = base64.urlsafe_b64encode(headers_json).decode("utf-8").rstrip("=")
        # AppSync requires payload to be base64-encoded '{}' -> 'e30='
        return f"{WS_ENDPOINT}?header={headers_b64}&payload=e30="

    def _parse_event(self, data: dict[str, Any]) -> CloudStreamEvent | None:
        """Parse a pushed GraphQL subscription message payload."""
        try:
            device_state = (
                data.get("payload", {}).get("data", {}).get("onUpdateDeviceStateTable")
            )
            if not device_state:
                return None

            device_uuid = device_state.get("PK", "")
            sk = device_state.get("SK", "")
            timestamp_val = device_state.get("TimeStamp")

            try:
                if timestamp_val:
                    updated_at = datetime.datetime.fromtimestamp(
                        int(timestamp_val), datetime.timezone.utc
                    )
                else:
                    updated_at = datetime.datetime.now(datetime.timezone.utc)
            except (ValueError, TypeError):
                updated_at = datetime.datetime.now(datetime.timezone.utc)

            inner_data_str = device_state.get("Data")

            # Route parsing based on Sort Key (SK) type
            if sk == "RSSI":
                rssi_val = 0
                if inner_data_str:
                    try:
                        rssi_val = int(inner_data_str)
                    except ValueError:
                        pass
                return RssiStateEvent(
                    satellite_id=self._satellite_id,
                    device_uuid=device_uuid,
                    updated_at=updated_at,
                    rssi=rssi_val,
                )

            elif sk == "Event#RainSensorState":
                is_wet = False
                if inner_data_str:
                    try:
                        inner_data = json.loads(inner_data_str)
                        if isinstance(inner_data, dict):
                            is_wet = str(inner_data.get("state")) == "1"
                        else:
                            is_wet = str(inner_data) == "1"
                    except Exception:
                        pass
                return RainSensorStateEvent(
                    satellite_id=self._satellite_id,
                    device_uuid=device_uuid,
                    updated_at=updated_at,
                    is_wet=is_wet,
                )

            elif sk.startswith("Station"):
                try:
                    zone_num = int(sk[7:])
                except ValueError:
                    return None

                is_watering = False
                remain_seconds = None
                program_number = None

                if inner_data_str:
                    try:
                        inner_data = json.loads(inner_data_str)
                        if isinstance(inner_data, dict):
                            is_watering = str(inner_data.get("state")) == "1"
                            remain_seconds = inner_data.get("remainSec")
                            program_number = inner_data.get("programNumber")
                    except Exception:
                        pass

                # If remain_seconds is an epoch timestamp, convert to relative duration
                if (
                    remain_seconds is not None
                    and remain_seconds > 1000000000
                    and timestamp_val
                ):
                    try:
                        server_ts = int(timestamp_val)
                        if remain_seconds >= server_ts:
                            remain_seconds -= server_ts
                    except (ValueError, TypeError):
                        pass

                return StationStateEvent(
                    satellite_id=self._satellite_id,
                    device_uuid=device_uuid,
                    updated_at=updated_at,
                    zone=zone_num,
                    is_watering=is_watering,
                    remaining_seconds=remain_seconds,
                    program_number=program_number,
                )

            elif sk == "Connected":
                is_connected = True
                active_station = None
                remain_seconds = None
                rain_delay = None

                if inner_data_str:
                    try:
                        inner_data = json.loads(inner_data_str)
                        if isinstance(inner_data, dict):
                            active_station = inner_data.get("activeStation")
                            remain_seconds = inner_data.get("remainSec")
                            rain_delay = inner_data.get("rainDelay")
                            if str(inner_data.get("state")) in ("0", "offline"):
                                is_connected = False
                        else:
                            if str(inner_data) in ("0", "offline"):
                                is_connected = False
                    except Exception:
                        pass

                # Epoch check for remaining seconds
                if (
                    remain_seconds is not None
                    and remain_seconds > 1000000000
                    and timestamp_val
                ):
                    try:
                        server_ts = int(timestamp_val)
                        if remain_seconds >= server_ts:
                            remain_seconds -= server_ts
                    except (ValueError, TypeError):
                        pass

                return ConnectionStatusEvent(
                    satellite_id=self._satellite_id,
                    device_uuid=device_uuid,
                    updated_at=updated_at,
                    is_connected=is_connected,
                    active_station=active_station,
                    remaining_seconds=remain_seconds,
                    rain_delay=rain_delay,
                )

            # Fallback for unrecognized sort keys (future proofing)
            return GenericCloudStreamEvent(
                satellite_id=self._satellite_id,
                device_uuid=device_uuid,
                updated_at=updated_at,
                event_key=sk,
                raw_data=inner_data_str,
            )
        except Exception as e:
            _LOGGER.error("Error parsing stream event: %s", e)
            return None

    async def listen(self) -> AsyncIterator[CloudStreamEvent]:
        """Establish a connection to the WebSocket and yield events in real-time.

        Automatically manages heartbeats, reconnections, and token lifecycle.
        """
        backoff = INITIAL_BACKOFF
        max_backoff = MAX_BACKOFF

        while True:
            ws = None
            try:
                # 1. Fetch current access token
                try:
                    token = await self._token_provider.async_get_token(
                        force_refresh=self._force_refresh_token
                    )
                    # Reset force refresh on successful token retrieval
                    self._force_refresh_token = False
                except Exception as token_err:
                    _LOGGER.error(
                        "Failed to retrieve authentication token: %s", token_err
                    )
                    raise RainbirdAuthException(
                        "Token acquisition failed"
                    ) from token_err

                url = self._get_connection_url(token)
                _LOGGER.debug("Connecting to AppSync WebSocket endpoint...")

                async with self._session.ws_connect(
                    url, protocols=["graphql-ws"]
                ) as ws:
                    _LOGGER.debug(
                        "WebSocket connection opened. Initializing protocol..."
                    )
                    backoff = (
                        INITIAL_BACKOFF  # Reset backoff upon successful connection
                    )

                    # 2. Send connection_init
                    await ws.send_json({"type": "connection_init"})

                    # 3. Read message loop
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = msg.json()
                            msg_type = data.get("type")

                            if msg_type == "connection_ack":
                                _LOGGER.info(
                                    "Connection acknowledged. Registering subscription..."
                                )
                                # Subscribe once connection is acknowledged
                                sub_payload = {
                                    "id": "sub_device_state",
                                    "type": "start",
                                    "payload": {
                                        "data": json.dumps(
                                            {
                                                "query": "subscription onUpdateDeviceStateTable($PK : String!) {\n  onUpdateDeviceStateTable(PK: $PK) {\n    PK\n    SK\n    Data\n    TimeStamp\n  }\n}",
                                                "variables": {"PK": self._device_uuid},
                                            }
                                        ),
                                        "extensions": {
                                            "authorization": {
                                                "host": API_HOST,
                                                "Authorization": token,
                                            }
                                        },
                                    },
                                }
                                await ws.send_json(sub_payload)

                            elif msg_type == "data":
                                event = self._parse_event(data)
                                if event:
                                    yield event

                            elif msg_type == "ka":
                                # Keep-alive heartbeat received
                                _LOGGER.debug(
                                    "AppSync WebSocket keep-alive heartbeat received."
                                )

                            elif msg_type in ("connection_error", "error"):
                                payload = data.get("payload", {})
                                errors = payload.get("errors", [])
                                error_msg = (
                                    errors[0].get("message")
                                    if errors
                                    else "Unknown error"
                                )
                                _LOGGER.error(
                                    "AppSync server returned error: %s (type: %s)",
                                    error_msg,
                                    msg_type,
                                )

                                is_auth_error = False
                                # Check if authorization failed
                                for err in errors:
                                    if (
                                        "unauthorized" in err.get("message", "").lower()
                                        or err.get("errorType")
                                        == "UnauthorizedException"
                                    ):
                                        _LOGGER.warning(
                                            "Authorization error detected. Forcing token refresh."
                                        )
                                        self._force_refresh_token = True
                                        is_auth_error = True

                                if is_auth_error:
                                    break
                                else:
                                    raise RainbirdAuthException(
                                        f"WebSocket protocol error: {error_msg}"
                                    )

                            elif msg_type == "complete":
                                _LOGGER.info(
                                    "Subscription registration was terminated by server."
                                )
                                break

                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSE,
                            aiohttp.WSMsgType.CLOSING,
                            aiohttp.WSMsgType.CLOSED,
                        ):
                            _LOGGER.warning("WebSocket closing/closed: %s", msg.data)
                            break

            except asyncio.CancelledError:
                _LOGGER.info("WebSocket connection cancelled by caller.")
                if ws and not ws.closed:
                    await ws.close()
                break

            except RainbirdAuthException as auth_err:
                _LOGGER.error(
                    "Fatal authentication error in WebSocket stream: %s", auth_err
                )
                if ws and not ws.closed:
                    await ws.close()
                raise

            except Exception as e:
                _LOGGER.warning(
                    "WebSocket error encountered: %s. Retrying in %ss...", e, backoff
                )
                # If we get a 401 response status, force a token refresh next time
                if isinstance(e, aiohttp.ClientResponseError) and e.status == 401:
                    _LOGGER.warning(
                        "Received 401 response status. Forcing token refresh."
                    )
                    self._force_refresh_token = True

            # Reconnection backoff
            await asyncio.sleep(backoff)
            backoff = min(backoff * BACKOFF_FACTOR, max_backoff)
