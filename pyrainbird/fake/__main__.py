"""Command Line Interface for running the fake Rain Bird server."""

import argparse
import asyncio
import logging
import sys

from pyrainbird.fake.server import RainbirdFakeServer

# Configure basic logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

_LOGGER = logging.getLogger("pyrainbird.fake")


async def main() -> None:
    """Parse command line arguments and run the fake server."""
    parser = argparse.ArgumentParser(
        description="Run a fake Rain Bird device server for local testing and firmware extraction."
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="IP address to bind the servers to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="TCP port for the HTTP stick server (default: 8080, note: real controllers use 80)",
    )
    parser.add_argument(
        "--udp-port",
        type=int,
        default=33667,
        help="UDP port for the discovery server (default: 33667)",
    )
    parser.add_argument(
        "--mac",
        default="44:2c:05:00:11:22",
        help="MAC address to return in Legacy discovery mode (default: 44:2c:05:00:11:22)",
    )
    parser.add_argument(
        "--uuid",
        default="123e4567-e89b-12d3-a456-426614174000",
        help="UUID to return in Upgraded discovery mode (default: 123e4567-e89b-12d3-a456-426614174000)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Optional controller password/PIN. If set, payloads must be encrypted.",
    )
    parser.add_argument(
        "--output-dir",
        default="./extracted_fw",
        help="Directory to save downloaded firmware files (default: ./extracted_fw)",
    )

    args = parser.parse_args()

    server = RainbirdFakeServer(
        mac_address=args.mac,
        uuid_str=args.uuid,
        password=args.password,
        host=args.host,
        port=args.port,
        udp_port=args.udp_port,
        output_dir=args.output_dir,
    )

    await server.start()
    _LOGGER.info("Fake Rain Bird server is running. Press Ctrl+C to stop.")

    try:
        # Keep running until interrupted
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        _LOGGER.info("Stopping fake server...")
    finally:
        await server.stop()
        _LOGGER.info("Server stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
