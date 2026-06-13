# Library Architecture & Client Design Specification

This document details the software architecture, instantiation patterns, and capability-based abstraction layer designed to support newer firmware (Rain Bird 2.0 / IQ4) alongside legacy local controllers within `pyrainbird`.

---

## 1. High-Level Architecture: Capabilities over Protocol Details

Historically, `pyrainbird` exposed concrete transport-specific clients. To shield home automation systems and other library callers from protocol differences (such as local JSON-RPC over Port 80, local AES-encrypted HTTPS over Port 443, or Cloud-based REST APIs), the client library abstracts transport behaviors behind a unified capability interface.

```
              +------------------------------------------+
              |      Home Automation Client / Caller     |
              +--------------------+---------------------+
                                   |
                     [ Unified Abstract Controller ]
                                   |
         +-------------------------+-------------------------+
         |                                                   |
+--------v----------------------+                 +----------v------------------+
| AsyncRainbirdLocalController  |                 | AsyncRainbirdCloudController|
| - Local HTTP / JSON-RPC       |                 | - Cloud REST / JWT Auth     |
| - Local HTTPS / AES           |                 | - iq4server.rainbird.com    |
+-------------------------------+                 +-----------------------------+
```

---

## 2. Capability Feature Modeling (Enums)

Rather than query booleans or check subclass types to determine device capabilities, the library models capabilities as a set of features using a StrEnum:

```python
import enum

class ControllerFeature(enum.StrEnum):
    RAIN_DELAY = "rain_delay"
    SEASONAL_ADJUST = "seasonal_adjust"
    FORECAST_DELAY = "forecast_delay"
    ZONE_IRRIGATION = "zone_irrigation"
    CALENDAR_SCHEDULE = "calendar_schedule"
```

### The Abstract Controller Interface
Every controller implementation extends the base class `RainbirdController`, exposing its specific capabilities:

```python
class RainbirdController:
    """Abstract base class representing a Rain Bird controller's capabilities."""

    @property
    def supported_features(self) -> set[ControllerFeature]:
        """Return the features supported by this specific controller."""
        raise NotImplementedError()

    @property
    def max_zones(self) -> int:
        """Return the maximum number of stations supported."""
        raise NotImplementedError()

    @property
    def max_programs(self) -> int:
        """Return the maximum number of programs supported."""
        raise NotImplementedError()

    async def irrigate_zone(self, zone: int, minutes: int) -> None:
        """Turn on irrigation for a single zone."""
        raise NotImplementedError()

    async def stop_irrigation(self) -> None:
        """Turn off all active irrigation zones."""
        raise NotImplementedError()

    async def get_zone_states(self) -> States:
        """Return which zones are currently active."""
        raise NotImplementedError()

    async def get_rain_sensor_state(self) -> bool:
        """Return True if the rain sensor is active."""
        raise NotImplementedError()

    async def get_rain_delay(self) -> int:
        """Return the remaining rain delay in days."""
        raise NotImplementedError()

    async def set_rain_delay(self, days: int) -> None:
        """Set or clear a rain delay."""
        raise NotImplementedError()
```

---

## 3. Instantiation & progressive Setup Flows

Depending on how the user connects their device, the home automation client runs through one of two setup journeys. The library provides dedicated, explicit entry points to support these flows.

### Setup Flow Decision Tree

```
                          +-------------------------------+
                          |    User Adds Rain Bird IP     |
                          +---------------+---------------+
                                          |
                                    [ Probe IP ]
                                          |
                        +-----------------+-----------------+
                        |                                   |
                [ Port 80 Open ]                    [ Port 443 Open ]
                        |                                   |
              (Legacy Local Mode)                  (Upgraded Firmware)
                        |                                   |
             Prompt: Local Password                Prompt: Cloud Login
                        |                                   |
            Save: Host + Password                 Authenticate & Get Satellites
                                                            |
                                                   Save: Satellite ID + Token
```

### Journey A: Local Host/IP Setup (Probing)
1. **Local Network Probing:** The client probes the local network at the user's entered IP address.
2. **Device Detection:**
   - **Port 80 Open:** The device is running legacy HTTP firmware.
     - *Client Action:* Prompt the user for the local device password.
     - *Instantiation:* Call `create_local_controller(session, host, password)`.
   - **Port 443 Open (HTTPS):** The device is running upgraded/newer firmware.
     - *Client Action:* Inform the user that they must sign in using their Rain Bird cloud account.
     - *Next Step:* Redirect to **Journey B**.

### Journey B: Cloud Account Sign-In
1. **Authentication:** The client prompts the user for cloud credentials and calls `async_authenticate_cloud`.
2. **Satellite Discovery:** The helper verifies the credentials and returns the JWT token and a list of registered satellites associated with the user's account.
3. **Instantiation:** The user selects a satellite, and the client calls `create_cloud_controller(...)` to initialize the runtime controller.

---

## 4. API Reference

### A. Local Controller Factory
```python
from pyrainbird.async_client import create_local_controller

# Instantiates local controller (auto-probes and handles HTTP or HTTPS+AES transparently)
controller = await create_local_controller(
    session=clientsession,
    host="192.168.1.15",
    password="my_device_password",
)
```
- **Returns:** `AsyncRainbirdLocalController` (implements `RainbirdController`).
- **Features supported:** Typically `{ControllerFeature.RAIN_DELAY, ControllerFeature.SEASONAL_ADJUST, ControllerFeature.ZONE_IRRIGATION, ControllerFeature.CALENDAR_SCHEDULE}`.

### B. Cloud Authentication Helper
```python
from pyrainbird.cloud.client import async_authenticate_cloud

# Authenticates with iq4server.rainbird.com and returns token + registered controllers
token, satellites = await async_authenticate_cloud(
    session=clientsession,
    username="user@example.com",
    password="cloud_password",
)
```
- **Returns:** `tuple[str, list[CloudSatellite]]`.

### C. Cloud Controller Factory
```python
from pyrainbird.cloud.client import create_cloud_controller

# Instantiates cloud controller with a refreshed token callback
controller = create_cloud_controller(
    session=clientsession,
    token=token,
    satellite_id=satellites[0].id,
    async_get_access_token=my_token_refresher_callback,
)
```
- **Returns:** `AsyncRainbirdCloudController` (implements `RainbirdController`).
- **Features supported:** `{ControllerFeature.RAIN_DELAY, ControllerFeature.FORECAST_DELAY, ControllerFeature.SEASONAL_ADJUST, ControllerFeature.ZONE_IRRIGATION}`.

---

## 5. Token Refresh API Callback Callback

To avoid managing authentication persistence state inside `pyrainbird`, the client provides an `async_get_access_token` callback hook. If the cloud REST client receives an `HTTP 401 Unauthorized` response:
1. It executes the registered callback `async_get_access_token()`.
2. The home automation client retrieves a fresh token from its config session cache and returns it.
3. `pyrainbird` updates its active headers and retries the original request.
4. If no callback is registered, or the callback fails, a `RainbirdAuthException` is raised.
