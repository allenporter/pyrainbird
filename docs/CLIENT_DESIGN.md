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

    async def get_schedule(self) -> Schedule:
        """Return the controller's irrigation schedule.

        For cloud controllers, the REST responses (program list and assigned runtimes)
        are mapped internally to return the unified `Schedule` object, allowing the
        same timeline/calendar helpers to be reused.
        """
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
                                                   Save: Satellite ID + Auth Config
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

### Journey B: Cloud Account Sign-In (Programmatic & Web OAuth Flows)
1. **Authentication:** The client prompts the user for cloud credentials or guides them through a web authentication flow.
   - **OAuth 2.0 Implicit Grant & Redirect Restrictions:** The Rain Bird backend employs a standard OIDC/OAuth 2.0 Implicit Grant flow. Because the server-side identity provider configuration statically restricts redirection to `https://iq4.rainbird.com/auth.html` and does not support registering external redirect URIs (e.g. custom home automation callback URLs), standard automatic OIDC redirect loops back to local automation clients cannot be used.
   - **Authentication Options for Callers:** To accommodate different frontend surfaces, callers can authenticate using one of three patterns:
     - **Programmatic Credentials Flow (Default):** The library's `async_authenticate_cloud` function emulates a headless browser. It initiates the OIDC authorization request, parses the CSRF verification token from the login page, POSTs the credentials, and extracts the JWT `access_token` from the final redirect URL location headers.
     - **WebView Navigation Interception:** Callers running in environments with embedded browser widgets (e.g. mobile apps, Electron, or Tauri) can open the authorization URL in a WebView. The application monitors navigation events, detects when the page redirects to `https://iq4.rainbird.com/auth.html#access_token=...`, extracts the token from the fragment, and closes the WebView.
     - **Manual Copy-Paste Redirect:** Callers can redirect the user's external browser to the OIDC authorization page. After successful authentication, the user is redirected to the static `https://iq4.rainbird.com/auth.html#access_token=...` page. The user is then prompted to copy the redirected URL from their browser's address bar and paste it back into the client setup UI to complete authentication.
2. **Satellite Discovery:** The helper verifies the credentials and returns a list of registered satellites associated with the user's account, along with the initial access token.
   - **Account-based Setup:** The config flow behaves as an *account-based* discovery flow. It discovers all controllers under the user's account and registers a separate device/config entry for each `satellite_id`.
   - **Device-based Runtime:** Once configured, each device/config entry is managed independently, instantiating its own `RainbirdController` with its specific `satellite_id` at runtime.
3. **Instantiation:** The client instantiates a `RainbirdTokenProvider` for the entry and calls `create_cloud_controller(...)` to initialize the runtime controller.

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

# Authenticates with iq4server.rainbird.com and returns initial token + registered satellites
token, satellites = await async_authenticate_cloud(
    session=clientsession,
    username="user@example.com",
    password="cloud_password",
)
```
- **Returns:** `tuple[str, list[CloudSatellite]]`.

### C. Token Provider Interface
To avoid managing authentication lifecycle and persistence details inside `pyrainbird`, the client defines an abstract token provider class. Callers implement this interface to coordinate token caching, storage, and renewal:

```python
class RainbirdTokenProvider:
    """Interface for managing OAuth JWT authentication tokens."""

    async def async_get_token(self, force_refresh: bool = False) -> str:
        """Return a valid Bearer token.

        If `force_refresh` is True, bypasses local caches to request a fresh token.
        """
        raise NotImplementedError()
```

### D. Cloud Controller Factory
```python
from pyrainbird.cloud.client import create_cloud_controller

# Instantiates cloud controller using the token provider
controller = create_cloud_controller(
    session=clientsession,
    token_provider=token_provider,
    satellite_id=satellites[0].id,
)
```
- **Returns:** `AsyncRainbirdCloudController` (implements `RainbirdController`).
- **Features supported:** `{ControllerFeature.RAIN_DELAY, ControllerFeature.FORECAST_DELAY, ControllerFeature.SEASONAL_ADJUST, ControllerFeature.ZONE_IRRIGATION}`.

---

## 5. Token Provider Responsibilities & Error Handling

During API requests, the cloud controller queries `await token_provider.async_get_token()` to populate the `Authorization` header.

If the REST endpoint returns an `HTTP 401 Unauthorized` response:
1. The client invokes `await token_provider.async_get_token(force_refresh=True)` to force a token renewal.
2. The client retries the failed API request exactly once with the fresh token.
3. If the request fails again with a 401, a `RainbirdAuthException` is raised to the caller, signaling that re-authentication or setup credentials verification is required.
