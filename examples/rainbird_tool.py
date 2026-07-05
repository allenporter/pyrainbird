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
import logging
import os
from typing import Any

import aiohttp

from pyrainbird import async_client
from pyrainbird.cloud import (
    AsyncRainbirdCloudClient,
    AsyncRainbirdCloudStream,
    CachingTokenProvider,
    ConnectionStatusEvent,
    GenericCloudStreamEvent,
    RainSensorStateEvent,
    RssiStateEvent,
    StationStateEvent,
    create_cloud_controller,
)

_LOGGER = logging.getLogger(__name__)


def create_cloud_client(session: aiohttp.ClientSession) -> AsyncRainbirdCloudClient:
    """Create AsyncRainbirdCloudClient from environment variables."""
    username = os.environ.get("RAINBIRD_CLOUD_USERNAME") or os.environ.get(
        "RAINBIRD_USERNAME"
    )
    password = os.environ.get("RAINBIRD_CLOUD_PASSWORD") or os.environ.get(
        "RAINBIRD_PASSWORD"
    )
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


async def discover_local(timeout: float = 5.0) -> None:
    """Broadcast UDP discovery ping to find controllers on the local network."""
    import socket
    import select

    DISCOVERY_PAYLOAD = "RBD-ANDROID"
    PORTS = [33667, 33668]

    def do_discover():
        # Ephemeral broadcast socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)

        # Upgraded socket listening on port 33668
        upgraded_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            upgraded_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                upgraded_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except AttributeError:
                pass
            upgraded_sock.bind(("0.0.0.0", 33668))
            upgraded_sock.setblocking(False)
            has_upgraded = True
        except Exception as e:
            _LOGGER.warning(
                "Could not bind to port 33668 for upgraded discovery: %s", e
            )
            has_upgraded = False

        print("Sending discovery broadcast for local Rain Bird devices...")
        try:
            import time

            for port in PORTS:
                sock.sendto(DISCOVERY_PAYLOAD.encode(), ("255.255.255.255", port))

            print(f"Listening for responses for {timeout} seconds...")
            start_time = time.time()
            sockets_to_watch = [sock]
            if has_upgraded:
                sockets_to_watch.append(upgraded_sock)

            while True:
                elapsed = time.time() - start_time
                remaining = timeout - elapsed
                if remaining <= 0:
                    break

                readable, _, _ = select.select(
                    sockets_to_watch, [], [], max(0.1, remaining)
                )
                for r_sock in readable:
                    data, addr = r_sock.recvfrom(1024)
                    mode = "Upgraded" if r_sock is upgraded_sock else "Legacy"
                    print(f"\n[+] Found Device ({mode} Mode)!")
                    print(f"    IP Address: {addr[0]}")
                    print(f"    Response (Hex): {data.hex().upper()}")
                    try:
                        decoded = data.decode("utf-8")
                        print(f"    Response (String): {decoded}")
                    except Exception:
                        pass
        except Exception as e:
            print(f"Error during discovery: {e}")
        finally:
            sock.close()
            if has_upgraded:
                upgraded_sock.close()
        print("\n--- Local discovery finished. ---")

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, do_discover)


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

    # Add discover_local subcommand
    discover_local_parser = subcommand_parsers.add_parser(
        "discover_local",
        help="Broadcast UDP discovery ping to find controllers on the local network",
    )
    discover_local_parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Time to listen for responses (default: 5.0 seconds)",
    )
    discover_local_parser.set_defaults(func=None)

    # Add request_fw_update subcommand
    fw_update_parser = subcommand_parsers.add_parser(
        "request_fw_update",
        help="Trigger a firmware update on the controller, pointing to a specific URL",
    )
    fw_update_parser.add_argument(
        "--lnk-update-url",
        default="",
        help="URL for LNK module firmware (e.g. http://10.10.38.83:8080/lnkfw/)",
    )
    fw_update_parser.add_argument(
        "--unv-update-url",
        default="",
        help="URL for universal panel controller firmware (e.g. http://10.10.38.83:8080/rbfw/firmware.bin)",
    )
    fw_update_parser.set_defaults(func=None)

    # Add get_fw_update_status subcommand
    fw_status_parser = subcommand_parsers.add_parser(
        "get_fw_update_status",
        help="Query the current firmware update status on the controller",
    )
    fw_status_parser.set_defaults(func=None)

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
        if args.command == "discover_local":
            await discover_local(args.timeout)
            return

        elif args.command == "discover_cloud":
            await discover_cloud(session, args.config_file)
            return

        elif args.command == "stream_cloud":
            await stream_cloud(session, args.config_file, args.satellite_id)
            return

        elif args.command == "request_fw_update":
            host = os.environ["RAINBIRD_SERVER"]
            password = os.environ["RAINBIRD_PASSWORD"]
            controller = await async_client.create_controller(session, host, password)
            result = await controller._local_client.request(
                "requestFwUpdate",
                {
                    "lnk_update_url": args.lnk_update_url,
                    "unv_update_url": args.unv_update_url,
                },
            )
            print(result)
            return

        elif args.command == "get_fw_update_status":
            host = os.environ["RAINBIRD_SERVER"]
            password = os.environ["RAINBIRD_PASSWORD"]
            controller = await async_client.create_controller(session, host, password)
            result = await controller._local_client.request("getFwUpdateStatus")
            print(result)
            return

        satellite_id_str = os.environ.get("RAINBIRD_SATELLITE_ID")
        if satellite_id_str:
            satellite_id = int(satellite_id_str)
            username = os.environ.get("RAINBIRD_CLOUD_USERNAME") or os.environ.get(
                "RAINBIRD_USERNAME"
            )
            password = os.environ.get("RAINBIRD_CLOUD_PASSWORD") or os.environ.get(
                "RAINBIRD_PASSWORD"
            )

            client = AsyncRainbirdCloudClient(session, username, password)
            token_provider = CachingTokenProvider(client, args.config_file)
            client.token_provider = token_provider

            controller = create_cloud_controller(session, token_provider, satellite_id)
        else:
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
