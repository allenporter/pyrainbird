#!/usr/bin/env python3
"""A command line tool for issuing commands to rainbird.

All commands supported by `AsyncRainbirdController` are supported as
commands for the tool.

```
$ export RAINBIRD_SERVER=192.168.1.10
$ export RAINBIRD_PASSWORD=mypass
$ ./rainbird_tool --help
$ ./rainbird_tool get_wifi_settings
```
"""

import argparse
import asyncio
import datetime
import inspect
import json
import logging
import os
from typing import Any

import aiohttp

from pyrainbird import async_client
from pyrainbird.cloud import (
    AsyncRainbirdCloudClient,
    AsyncRainbirdCloudStream,
    ConnectionStatusEvent,
    GenericCloudStreamEvent,
    RainSensorStateEvent,
    RssiStateEvent,
    StationStateEvent,
)

_LOGGER = logging.getLogger(__name__)


CACHE_FILE_MODE = 0o600


class CachingTokenProvider(async_client.RainbirdTokenProvider):
    """Token provider that caches the cloud token in a JSON file."""

    def __init__(
        self,
        client: AsyncRainbirdCloudClient,
        config_path: str,
    ) -> None:
        """Initialize CachingTokenProvider."""
        self._client = client
        self._config_path = config_path
        self._client.token_provider = self

    def _save_token_to_cache(self, token: str) -> None:
        """Save the token to the JSON config file."""
        try:
            os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump({"token": token}, f, indent=2)
            os.chmod(self._config_path, CACHE_FILE_MODE)
        except Exception as err:
            _LOGGER.warning("Failed to save token to cache: %s", err)

    async def async_get_token(self, force_refresh: bool = False) -> str:
        """Return a valid token, checking env, reading cache, or logging in."""
        env_token = os.environ.get("RAINBIRD_CLOUD_TOKEN")
        if env_token:
            self._client._token = env_token
            self._client._headers["Authorization"] = f"Bearer {env_token}"
            return env_token

        if not force_refresh and self._client.token:
            return self._client.token

        if not force_refresh and os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    token = config.get("token")
                if token:
                    self._client._token = token
                    self._client._headers["Authorization"] = f"Bearer {token}"
                    return token
            except Exception as err:
                _LOGGER.warning("Failed to read token from cache: %s", err)

        if not self._client._username or not self._client._password:
            raise async_client.RainbirdAuthException(
                "No cached token found and credentials (RAINBIRD_CLOUD_USERNAME/RAINBIRD_CLOUD_PASSWORD) are not set."
            )

        _LOGGER.info("Logging in to obtain a new token...")
        token = await self._client.login()
        self._save_token_to_cache(token)
        return token


def create_cloud_client(session: aiohttp.ClientSession) -> AsyncRainbirdCloudClient:
    """Create AsyncRainbirdCloudClient from environment variables."""
    username = os.environ.get("RAINBIRD_CLOUD_USERNAME")
    password = os.environ.get("RAINBIRD_CLOUD_PASSWORD")
    return AsyncRainbirdCloudClient(session, username=username, password=password)


async def discover_cloud(session: aiohttp.ClientSession, config_file: str) -> None:
    """Authenticate with the cloud and list registered satellites/controllers."""
    client = create_cloud_client(session)
    token_provider = CachingTokenProvider(client, config_file)
    client.token_provider = token_provider

    try:
        satellites = await client.get_satellites()
        token = await token_provider.async_get_token()
        print(f"Authentication successful! Token: {token[:10]}...")
        print(f"Satellites found: {len(satellites)}")
        for sat in satellites:
            print(f"- ID: {sat.id}")
            print(f"  Name: {sat.name}")
            print(f"  Type: {sat.type}")
            print(f"  Site ID: {sat.site_id}")
            print(f"  Site Name: {sat.site_name}")
            print(f"  Station Count: {sat.station_count}")
            print(f"  Description: {sat.description}")
    except Exception as err:
        print(f"Cloud discovery failed: {err}")


async def stream_cloud(
    session: aiohttp.ClientSession, config_file: str, satellite_id: int
) -> None:
    """Connect to the cloud real-time updates WebSocket stream."""
    client = create_cloud_client(session)
    token_provider = CachingTokenProvider(client, config_file)
    client.token_provider = token_provider

    try:
        satellites = await client.get_satellites()

        # Find the device_uuid for the given satellite_id
        device_uuid = None
        for sat in satellites:
            if sat.id == satellite_id:
                device_uuid = sat.device_uuid
                break

        if not device_uuid:
            print(f"Error: Satellite ID {satellite_id} not found in user account.")
            return

        print(
            f"Connecting to real-time updates stream for satellite {satellite_id} (UUID: {device_uuid})..."
        )
        stream = AsyncRainbirdCloudStream(
            token_provider, satellite_id, device_uuid, session
        )

        async for event in stream.listen():
            prefix = f"[{event.updated_at.isoformat()}] Satellite {event.satellite_id} ({event.device_uuid}) -"
            if isinstance(event, StationStateEvent):
                print(
                    f"{prefix} Station {event.zone} - Watering: {event.is_watering}, "
                    f"Remaining: {event.remaining_seconds}s, Program: {event.program_number}"
                )
            elif isinstance(event, RainSensorStateEvent):
                print(f"{prefix} Rain Sensor - Wet: {event.is_wet}")
            elif isinstance(event, ConnectionStatusEvent):
                print(
                    f"{prefix} Connection - Connected: {event.is_connected}, "
                    f"Active Station: {event.active_station}, "
                    f"Remaining: {event.remaining_seconds}s, Rain Delay: {event.rain_delay}"
                )
            elif isinstance(event, RssiStateEvent):
                print(f"{prefix} Signal - RSSI: {event.rssi}")
            elif isinstance(event, GenericCloudStreamEvent):
                print(
                    f"{prefix} Generic - Key: {event.event_key}, Data: {event.raw_data}"
                )
    except asyncio.CancelledError:
        print("Stream cancelled.")
    except Exception as err:
        print(f"Stream error: {err}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--log-level",
        default="warning",
        choices=["debug", "info", "warning", "error", "critical"],
        help="The log level",
    )
    parser.add_argument(
        "--config-file",
        default=os.path.expanduser("~/.config/rainbird.json"),
        help="Path to JSON configuration/token cache file (default: ~/.config/rainbird.json)",
    )

    subcommand_parsers = parser.add_subparsers(
        title="Commands", dest="command", required=True
    )

    # Add discover_cloud subcommand
    discover_parser = subcommand_parsers.add_parser(
        "discover_cloud",
        help="Authenticate with the cloud and list registered satellites/controllers",
    )
    discover_parser.set_defaults(func=None)

    # Add stream_cloud subcommand
    stream_parser = subcommand_parsers.add_parser(
        "stream_cloud",
        help="Connect to the cloud real-time updates WebSocket stream",
    )
    stream_parser.add_argument(
        "satellite_id",
        type=int,
        help="The satellite/controller ID to stream events for",
    )
    stream_parser.set_defaults(func=None)

    for method_name in dir(async_client.AsyncRainbirdController):
        if method_name.startswith("_"):
            continue
        method = getattr(async_client.AsyncRainbirdController, method_name)
        if not callable(method):
            continue

        # Try to get the signature of the method
        try:
            sig = inspect.signature(method)
        except ValueError:
            # Skip the method if it has no signature
            continue

        # Create a parser for the method
        method_parser = subcommand_parsers.add_parser(
            method_name, help=f"Call the {method_name} method"
        )
        method_parser.set_defaults(func=method)

        # Get the arguments of the method
        method_args = list(sig.parameters.keys())[1:]  # exclude 'self'
        # Add the arguments to the parser
        for arg in method_args:
            param = sig.parameters[arg]
            method_parser.add_argument(arg, default=param.default)

    return parser.parse_args()


def parse_value(value: Any) -> Any:
    """Parse the command line arg into a value."""
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        pass
    try:
        return datetime.time.fromisoformat(value)
    except ValueError:
        pass
    try:
        return int(value, 16)
    except ValueError:
        pass
    return str(value)


async def main():
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()))

    async with aiohttp.ClientSession() as session:
        if args.command == "discover_cloud":
            await discover_cloud(session, args.config_file)
            return

        elif args.command == "stream_cloud":
            await stream_cloud(session, args.config_file, args.satellite_id)
            return

        host = os.environ["RAINBIRD_SERVER"]
        password = os.environ["RAINBIRD_PASSWORD"]
        controller = await async_client.create_controller(session, host, password)
        method_args = {
            k: parse_value(v)
            for k, v in vars(args).items()
            if k not in {"func", "command", "log_level", "config_file"}
        }
        result = await args.func(controller, **method_args)
        print(result)


# Run the main function if this script is run
if __name__ == "__main__":
    asyncio.run(main())
