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
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from pyrainbird.async_client import RainbirdTokenProvider
from pyrainbird.exceptions import RainbirdAuthException

from .models import (
    CloudStreamEvent,
    CloudStreamSortKey,
    ConnectedData,
    ConnectionStatusEvent,
    DeviceStateRecord,
    GenericCloudStreamEvent,
    RainSensorStateEvent,
    RainSensorStateData,
    RssiStateEvent,
    StationStateData,
    StationStateEvent,
)

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
        if not isinstance(data, dict):
            return None

        device_state = (
            data.get("payload", {}).get("data", {}).get("onUpdateDeviceStateTable")
        )
        if not isinstance(device_state, dict):
            return None

        try:
            record = DeviceStateRecord.from_dict(device_state)
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Failed to parse device state record: %s", err)
            return None

        updated_at = record.updated_at

        # Route parsing based on Sort Key (SK) type
        if record.sk == CloudStreamSortKey.RSSI:
            rssi_val = 0
            if record.data:
                try:
                    rssi_val = int(record.data)
                except ValueError:
                    pass
            return RssiStateEvent(
                satellite_id=self._satellite_id,
                device_uuid=record.pk,
                updated_at=updated_at,
                rssi=rssi_val,
            )

        elif record.sk == CloudStreamSortKey.RAIN_SENSOR:
            is_wet = False
            if record.data:
                try:
                    sensor_data = RainSensorStateData.from_dict(json.loads(record.data))
                    is_wet = sensor_data.state == 1
                except (ValueError, TypeError, KeyError):
                    # Fallback for raw/scalar string format if not strict json dict
                    try:
                        # Parse as a dictionary manually to be safe
                        parsed_data = json.loads(record.data)
                        if isinstance(parsed_data, dict):
                            is_wet = str(parsed_data.get("state")) == "1"
                        else:
                            is_wet = str(parsed_data) == "1"
                    except (ValueError, TypeError, json.JSONDecodeError):
                        is_wet = str(record.data) == "1"
            return RainSensorStateEvent(
                satellite_id=self._satellite_id,
                device_uuid=record.pk,
                updated_at=updated_at,
                is_wet=is_wet,
            )

        elif record.sk.startswith(CloudStreamSortKey.STATION_PREFIX):
            try:
                zone_num = int(record.sk[len(CloudStreamSortKey.STATION_PREFIX) :])
            except ValueError:
                return None

            is_watering = False
            remain_seconds = None
            program_number = None

            if record.data:
                try:
                    station_data = StationStateData.from_dict(json.loads(record.data))
                    is_watering = station_data.state == 1
                    remain_seconds = station_data.remain_sec
                    program_number = station_data.program_number
                except (ValueError, TypeError, KeyError):
                    try:
                        # Fallback if structure changes or is slightly different
                        parsed_data = json.loads(record.data)
                        if isinstance(parsed_data, dict):
                            is_watering = str(parsed_data.get("state")) == "1"
                            remain_seconds = parsed_data.get("remainSec")
                            program_number = parsed_data.get("programNumber")
                    except (ValueError, TypeError, json.JSONDecodeError):
                        pass

            # If remain_seconds is an epoch timestamp, convert to relative duration
            if (
                remain_seconds is not None
                and remain_seconds > 1000000000
                and record.timestamp
            ):
                if remain_seconds >= record.timestamp:
                    remain_seconds -= record.timestamp

            return StationStateEvent(
                satellite_id=self._satellite_id,
                device_uuid=record.pk,
                updated_at=updated_at,
                zone=zone_num,
                is_watering=is_watering,
                remaining_seconds=remain_seconds,
                program_number=program_number,
            )

        elif record.sk == CloudStreamSortKey.CONNECTED:
            is_connected = True
            active_station = None
            remain_seconds = None
            rain_delay = None

            if record.data:
                try:
                    conn_data = ConnectedData.from_dict(json.loads(record.data))
                    active_station = conn_data.active_station
                    remain_seconds = conn_data.remain_sec
                    rain_delay = conn_data.rain_delay
                    if str(conn_data.state) in ("0", "offline"):
                        is_connected = False
                except (ValueError, TypeError, KeyError):
                    try:
                        parsed_data = json.loads(record.data)
                        if isinstance(parsed_data, dict):
                            active_station = parsed_data.get("activeStation")
                            remain_seconds = parsed_data.get("remainSec")
                            rain_delay = parsed_data.get("rainDelay")
                            if str(parsed_data.get("state")) in ("0", "offline"):
                                is_connected = False
                        else:
                            if str(parsed_data) in ("0", "offline"):
                                is_connected = False
                    except (ValueError, TypeError, json.JSONDecodeError):
                        pass

            # Epoch check for remaining seconds
            if (
                remain_seconds is not None
                and remain_seconds > 1000000000
                and record.timestamp
            ):
                if remain_seconds >= record.timestamp:
                    remain_seconds -= record.timestamp

            return ConnectionStatusEvent(
                satellite_id=self._satellite_id,
                device_uuid=record.pk,
                updated_at=updated_at,
                is_connected=is_connected,
                active_station=active_station,
                remaining_seconds=remain_seconds,
                rain_delay=rain_delay,
            )

        # Fallback for unrecognized sort keys (future proofing)
        return GenericCloudStreamEvent(
            satellite_id=self._satellite_id,
            device_uuid=record.pk,
            updated_at=updated_at,
            event_key=record.sk,
            raw_data=record.data,
        )

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
                except (
                    RainbirdAuthException,
                    aiohttp.ClientError,
                    TimeoutError,
                    ConnectionError,
                    OSError,
                ) as token_err:
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
                            try:
                                data = msg.json()
                            except (ValueError, TypeError) as json_err:
                                _LOGGER.warning(
                                    "Received invalid JSON message: %s", json_err
                                )
                                continue
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

            except (
                aiohttp.ClientError,
                TimeoutError,
                ConnectionError,
                OSError,
            ) as e:
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
