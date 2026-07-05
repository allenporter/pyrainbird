Python module for interacting with [WiFi LNK](https://www.rainbird.com/products/module-wi-fi-lnk) module of the Rain Bird Irrigation system. This project has no affiliation with Rain Bird.

This module communicates directly towards the IP Address of the WiFi module. You can start/stop the irrigation, get the currently active zone, and other controller settings. This library currently only has very limited cloud support. Also there are a number of Rain Bird devices with very different command APIs.

See [documentation](https://allenporter.github.io/pyrainbird/) for full quickstart and API reference.
See the [github project](https://github.com/allenporter/pyrainbird).

# Quickstart

This is an example usage to get the current irrigation state for all available
irrigation zones:
```python
import asyncio
import aiohttp
from pyrainbird import async_client

async def main() -> None:
    async with aiohttp.ClientSession() as session:
        controller: async_client.AsyncRainbirdController = await async_client.create_controller(
            session,
            "192.168.1.1",
            "password",
        )
        zones = await controller.get_available_stations()
        states = await controller.get_zone_states()
        for zone in zones.active_set:
            print(
                f"Sprinkler zone {zone}: {'active' if zone in states.active_set else 'inactive'}"
            )

asyncio.run(main())
```

See [examples](examples/) for additional details on how to use the APIs and an example command
line tool for querying the device.

# Compatibility

This library interacts with Rain Bird controllers using either **LNK1** (legacy) or **LNK2** (modern) Wi-Fi modules.

### LNK1 vs. LNK2 Modules
- **LNK1 Modules:** Communicate over plaintext HTTP (port 80), with payloads encrypted using the device password.
- **LNK2 Modules:** Communicate over HTTPS (port 443), with payloads encrypted using the device password.

### Local Connection Resiliency
Modern LNK2 modules (running firmware v4.x+) synchronize their state with the Rain Bird cloud shadow periodically (typically every 5 minutes). Because the ESP32 chip has highly constrained memory and runs a single serial Manchester line mutex, concurrent local polling during this cloud sync window can overload the hardware or cause watchdog crashes.

To smooth this over, this library implements:
- **Inter-Request Pacing:** A default 100ms pacing delay (`LOCAL_MIN_DELAY`) between consecutive local requests to prevent stack exhaustion.
- **Robust Retry & Backoff:** A 5-attempt exponential backoff retry wrapper to handle transient `503 Service Unavailable`, `Controller Busy` (`-32002`), and connection timeout states.

### Supported Controllers
We attempt to support standard controllers compatible with LNK1/LNK2 modules. However, because we do not own every controller hardware configuration, compatibility is not fully guaranteed for all models. Below is a breakdown of our current hardware support status:

#### Tier 1: Confirmed & Fully Supported
- **ESP-TM2** (Fully tested & verified against physical hardware)

#### Tier 2: Highly Likely to Work (Same Protocol Family)
These devices use the same JSON-RPC/SIP encapsulation (`tunnelSip`), standard program-based scheduling structures, and command sets as the ESP-TM2:
- **ESP-Me / ESP-ME3 / ESP-Me2** (Highly expected to work out-of-the-box; schedule formats are covered by library unit test mocks)
- **RC2 / ARC8** (Modern residential controllers sharing the standard TM2 family protocol layout)
- **TM2R / TRU**

#### Tier 3: Attempted / Untested & Complex (High Risk of Custom Timing/Structure issues)
These devices use different scheduling paradigms, binary layouts, or commercial specifications:
- **ESP-RZXe / ST8x-WiFi / ST8x-WiFi2** (Use independent-zone scheduling instead of program-based scheduling; scheduling retrieval has a custom, less-tested code branch)
- **LXME2 / LX-IVM / LX-IVM Pro** (Large-scale commercial 2-wire decoder panels with up to 40 programs and complex custom decoding logic)
- **TBOS-BT** (Battery-operated commercial controllers)

You are welcome to file an issue for improved compatibility with your device, especially if you include debug logs that capture the API responses from the device.

See [CONTRIBUTING](CONTRIBUTING.md) for details on developing in the library itself, such as
running the tests and other tooling used in development.
