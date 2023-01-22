Python module for interacting with [WiFi LNK](https://www.rainbird.com/products/module-wi-fi-lnk) module of the Rain Bird Irrigation system. This project has no affiliation with Rain Bird.

This module communicates directly towards the IP Address of the WiFi module. You can start/stop the irrigation, get the currently active zone, and other controller settings. This library currently only has very limited cloud support. Also there are a number of Rain Bird devices with very different command APIs.

See [documentation](https://allenporter.github.io/pyrainbird/) for full quickstart and API reference.
See the [github project](https://github.com/allenporter/pyrainbird).

# Quickstart

This is an example usage to get the current irrigation state for all available
irrigation zones:
```
import aiohttp
from pyrainbird import async_client

async with aiohttp.ClientSession() as client:
    controller: AsyncRainbirdController = async_client.CreateController(
        client,
        "192.168.1.1",
        "password"
    )
    zones = await controller.get_available_stations()
    states = await controller.get_zone_states()
    for zone in zones:
        if zone in states.active_set:
            print("Sprinkler zone {zone} is active")
```

See [examples](examples/) for additional details on how to use the APIs and an example command
line tool for querying the device.

# Compatibility

This library has been tested with the following devices:

  - ESP-TM2

You are welcome to file an issue for improved compatibility with your device especially if you
include debug logs that capture the API responses form the device.

See [CONTRIBUTING](CONTRIBUTING.md) for details on developing in the library itself, such as
running the tests and other tooling used in development.
