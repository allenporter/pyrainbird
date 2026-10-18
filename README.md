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

### Local Connection Resiliency & Troubleshooting
LNK1 and LNK2 modules run on a resource-constrained microcontroller communicating with the irrigation panel over a slow 19200-baud single-wire serial bus. On models known to return transient `503 Service Unavailable` responses when the serial line is busy (such as `ESP-ME`, `ESP-ME3`, and `ESP-RZXe`), this library automatically retries with exponential backoff.

On modern **LNK2** modules (firmware v4.x+), several firmware and hardware constraints cannot be bypassed in software and require network or setup adjustments if you experience local timeouts or disconnects:

- **Single Socket & Cloud Sync Contention:** The LNK2 local HTTPS server accepts only **1 concurrent socket** (`max_open_sockets = 1`) and processes local `/stick` commands on the same single-threaded state machine that handles background cloud synchronization and a 1,000 ms serial polling loop whenever cloud connectivity is active.
  - Avoid polling the controller from multiple local clients at the same time.
  - If you only use local control (e.g., Home Assistant) and experience periodic connection timeouts on controllers like the ESP-TM2, blocking the LNK2 module's internet access at your router/firewall disables the background cloud sync loop and leaves the local API uncontested.
- **2.4 GHz Wi-Fi & Dual-Band / Mesh APs:** The LNK2 2.4 GHz radio frequently drops connections or fails to roam when connected to combined 2.4/5 GHz SSIDs, band-steering networks, or multi-AP mesh systems. Placing the LNK2 on a dedicated **2.4 GHz-only SSID** (and pinning it to the closest access point) resolves most recurring Wi-Fi dropoffs.
- **Authentication Lockout (`403 Forbidden` / `-32001`):** LNK2, ARC8, and RC2 modules enforce a strict lockout on `/stick` after **3 failed password attempts**, rejecting all local requests for **15 minutes** (and resetting the 15-minute timer if another failed attempt occurs during the window). If you encounter `403 Forbidden` or lockout errors, stop all clients from polling the device and wait at least 15 minutes before retrying with the correct password.

### Supported Controllers
We attempt to support standard controllers compatible with LNK1/LNK2 modules. However, because we do not own every controller hardware configuration, compatibility is not fully guaranteed for all models. Below is a breakdown of our current hardware support status:

#### Tier 1: Confirmed & Fully Supported
- **ESP-TM2** (Fully tested & verified against physical hardware)

#### Tier 2: Likely to Work (Same Protocol Family)
These devices use the same JSON-RPC/SIP encapsulation (`tunnelSip`), standard program-based scheduling structures, and command sets as the ESP-TM2:
- **ESP-Me / ESP-ME3 / ESP-Me2** (Expected to work out-of-the-box; schedule formats are covered by library unit test mocks)
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
