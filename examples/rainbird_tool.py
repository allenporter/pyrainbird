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

_LOGGER = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--log-level",
        default="warning",
        choices=["debug", "info", "warning", "error", "critical"],
        help="The log level",
    )

    subcommand_parsers = parser.add_subparsers(
        title="Commands", dest="command", required=True
    )
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
    return int(value, 16)


async def main():
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()))

    host = os.environ["RAINBIRD_SERVER"]
    password = os.environ["RAINBIRD_PASSWORD"]

    async with aiohttp.ClientSession() as session:
        client = async_client.CreateController(session, host, password)
        method_args = {
            k: parse_value(v)
            for k, v in vars(args).items()
            if k != "func" and k != "command" and k != "log_level"
        }
        result = await args.func(client, **method_args)
        print(result)


# Run the main function if this script is run
if __name__ == "__main__":
    asyncio.run(main())
