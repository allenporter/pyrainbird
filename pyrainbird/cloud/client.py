"""Cloud client for rainbird IQ4 service."""

import asyncio
import datetime
import json
import logging
import os
import re
import urllib.parse
import uuid
from typing import Any
import aiohttp

from ..async_client import ControllerFeature, RainbirdController, RainbirdTokenProvider
from ..data import CloudSatellite, Schedule, States
from ..exceptions import (
    RainbirdApiException,
    RainbirdAuthException,
    RainbirdConnectionError,
)

_LOGGER = logging.getLogger(__name__)

AUTH_BASE = "https://iq4server.rainbird.com/coreidentityserver"
API_BASE = "https://iq4server.rainbird.com/coreapi/api"
CLIENT_ID = "C5A6F324-3CD3-4B22-9F78-B4835BA55D25"
REDIRECT_URI = "https://iq4.rainbird.com/auth.html"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


WAF_RETRY_INITIAL_BACKOFF = 10.0
WAF_RETRY_BACKOFF_INCREMENT = 10.0
WAF_RETRY_MAX_BACKOFF = 60.0


def _parse_login_validation_error(html: str) -> str | None:
    """Parse OIDC login page HTML to extract form validation errors or WAF/CAPTCHA signatures.

    Returns "WAF_CHALLENGE" if a WAF/CAPTCHA challenge is detected.
    """
    if (
        "challenge" in html.lower()
        or "captcha" in html.lower()
        or "waf" in html.lower()
        or "robot" in html.lower()
    ):
        return "WAF_CHALLENGE"

    # Search for validation summary errors
    re_match = re.search(
        r"validation-summary-errors.*?<li>([^<]+)</li>",
        html,
        re.DOTALL,
    )
    if re_match:
        return re_match.group(1).strip()

    # Search for field-level validation errors
    re_match = re.search(r"field-validation-error[^>]*>([^<]+)<", html)
    if re_match:
        return re_match.group(1).strip()

    # Search for generic text-danger validation messages
    re_match = re.search(r"text-danger[^>]*>([^<]+)<", html)
    if re_match:
        return re_match.group(1).strip()

    return None


class AsyncRainbirdCloudClient:
    """Rainbird cloud API client handling OIDC authentication and REST endpoints."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        token_provider: RainbirdTokenProvider | None = None,
    ) -> None:
        """Initialize AsyncRainbirdCloudClient."""
        self._session = session
        self._username = username
        self._password = password
        self._token = token
        self._token_provider = token_provider
        self._headers = {
            "Accept": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    @property
    def token(self) -> str | None:
        """Return the cached access token."""
        return self._token

    @property
    def token_provider(self) -> RainbirdTokenProvider | None:
        """Return the token provider."""
        return self._token_provider

    @token_provider.setter
    def token_provider(self, provider: RainbirdTokenProvider | None) -> None:
        """Set the token provider."""
        self._token_provider = provider

    async def login(self, max_retries: int = 3) -> str:
        """Authenticate using the OIDC Implicit Grant flow against ASP.NET Core Identity.

        This emulates a standard browser sign-in process required by Microsoft identity
        backends when direct REST credentials endpoints are unavailable. It performs the
        following steps:
        1. Initiates the OIDC authorize flow request.
        2. Retrieves the standard ASP.NET Antiforgery CSRF verification token
           (`__RequestVerificationToken`) from the HTML login form response.
        3. Form-posts the username, password, return URL, and verification token.
        4. Intercepts the final redirection fragment containing the JWT access token.
        """
        if not self._username or not self._password:
            raise RainbirdAuthException("Username and password are required to log in.")

        state = uuid.uuid4().hex[:16]
        nonce = uuid.uuid4().hex[:16]

        auth_url_params = {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "id_token token",
            "scope": "coreAPI.read coreAPI.write openid profile",
            "state": state,
            "nonce": nonce,
        }
        return_url = f"/coreidentityserver/connect/authorize/callback?{urllib.parse.urlencode(auth_url_params)}"

        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://iq4server.rainbird.com",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
        }

        backoff = WAF_RETRY_INITIAL_BACKOFF
        retries = 0
        while True:
            try:
                csrf_token = await self._get_csrf_token(return_url, headers)
                location = await self._submit_credentials(
                    return_url, csrf_token, headers
                )
                access_token_value = await self._follow_redirects(location, headers)
                break
            except Exception as err:
                if (
                    "202" in str(err)
                    or "challenge" in str(err).lower()
                    or "captcha" in str(err).lower()
                    or "waf" in str(err).lower()
                ):
                    retries += 1
                    if retries > max_retries:
                        raise RainbirdAuthException(
                            f"AWS WAF challenge page detected. Login blocked by WAF: {err}"
                        ) from err
                    _LOGGER.warning(
                        "AWS WAF challenge page detected. Retrying login in %.1f seconds...",
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(
                        backoff + WAF_RETRY_BACKOFF_INCREMENT, WAF_RETRY_MAX_BACKOFF
                    )
                else:
                    raise

        self._token = access_token_value
        self._headers["Authorization"] = f"Bearer {self._token}"
        return self._token

    async def _get_csrf_token(self, return_url: str, headers: dict[str, str]) -> str:
        """Fetch the login page and extract the CSRF token."""
        login_url = (
            f"{AUTH_BASE}/Account/Login?ReturnUrl={urllib.parse.quote(return_url)}"
        )
        try:
            async with self._session.get(login_url, headers=headers) as resp:
                if resp.status != 200:
                    raise RainbirdConnectionError(
                        f"Failed to fetch login page, HTTP status: {resp.status}"
                    )
                html = await resp.text()
        except aiohttp.ClientError as err:
            raise RainbirdConnectionError(
                f"Connection error fetching login page: {err}"
            ) from err

        match = re.search(
            r'name=["\']__RequestVerificationToken["\'].*?value=["\']([^"\']+)["\']',
            html,
            re.DOTALL,
        )
        if not match:
            match = re.search(
                r'value=["\']([^"\']+)["\'].*?name=["\']__RequestVerificationToken["\']',
                html,
                re.DOTALL,
            )

        if not match:
            raise RainbirdApiException(
                "Could not find __RequestVerificationToken in the page."
            )

        return match.group(1)

    async def _submit_credentials(
        self, return_url: str, csrf_token: str, headers: dict[str, str]
    ) -> str:
        """Submit login credentials and retrieve the initial redirect location."""
        post_url = (
            f"{AUTH_BASE}/Account/Login?ReturnUrl={urllib.parse.quote(return_url)}"
        )
        payload = {
            "Username": self._username,
            "Password": self._password,
            "ReturnUrl": return_url,
            "__RequestVerificationToken": csrf_token,
        }
        post_headers = {
            **headers,
            "Referer": post_url,
        }

        try:
            async with self._session.post(
                post_url, data=payload, headers=post_headers, allow_redirects=False
            ) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    error_msg = _parse_login_validation_error(html)
                    if error_msg == "WAF_CHALLENGE":
                        raise RainbirdConnectionError(
                            "AWS WAF challenge or captcha page detected under HTTP 200 status"
                        )
                    if error_msg:
                        raise RainbirdAuthException(
                            f"Invalid credentials or authentication failure: {error_msg}"
                        )
                    raise RainbirdAuthException(
                        "Invalid credentials or authentication failure."
                    )
                if resp.status not in (301, 302):
                    raise RainbirdAuthException(
                        f"Unexpected response status submitting credentials: {resp.status}"
                    )
                location = resp.headers.get("Location")
                if not location:
                    raise RainbirdAuthException(
                        "No redirect location returned after credentials submission."
                    )
                return location
        except aiohttp.ClientError as err:
            raise RainbirdConnectionError(
                f"Connection error submitting credentials: {err}"
            ) from err

    async def _follow_redirects(self, location: str, headers: dict[str, str]) -> str:
        """Follow the redirect chain manually to retrieve the access token."""
        max_redirects = 10
        redirects_followed = 0

        while location:
            if redirects_followed >= max_redirects:
                raise RainbirdAuthException(
                    "Maximum redirect limit reached during login."
                )

            if REDIRECT_URI in location:
                parsed_url = urllib.parse.urlparse(location)
                fragment = parsed_url.fragment
                params = urllib.parse.parse_qs(fragment)
                token_list = params.get("access_token")
                if token_list:
                    return token_list[0]
                else:
                    raise RainbirdAuthException(
                        "Reached redirect URI but could not find access_token in fragment."
                    )

            if location.startswith("/"):
                url = urllib.parse.urljoin(AUTH_BASE, location)
            else:
                url = location

            redirects_followed += 1
            try:
                async with self._session.get(
                    url, headers=headers, allow_redirects=False
                ) as resp:
                    if resp.status not in (301, 302):
                        raise RainbirdAuthException(
                            f"Redirection stopped prematurely at status {resp.status}."
                        )
                    location = resp.headers.get("Location")
            except aiohttp.ClientError as err:
                raise RainbirdConnectionError(
                    f"Connection error following login redirect: {err}"
                ) from err

        raise RainbirdAuthException(
            "Could not retrieve access token from redirect chain."
        )

    async def _async_get_token(self, force_refresh: bool = False) -> str:
        """Resolve the active bearer token, either via provider or stored token."""
        provider = self._token_provider or RainbirdCloudTokenProvider(self)
        token = await provider.async_get_token(force_refresh=force_refresh)
        self._token = token
        self._headers["Authorization"] = f"Bearer {token}"
        return token

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Perform a REST API request with automatic 401 token refresh retries."""
        url = f"{API_BASE}/{path}"
        await self._async_get_token()

        headers = {**self._headers, **kwargs.pop("headers", {})}

        try:
            async with self._session.request(
                method, url, headers=headers, **kwargs
            ) as resp:
                if resp.status == 401:
                    _LOGGER.info(
                        "Token expired (401) on %s %s, attempting refresh...",
                        method,
                        path,
                    )
                    await self._async_get_token(force_refresh=True)
                    headers["Authorization"] = f"Bearer {self._token}"
                    async with self._session.request(
                        method, url, headers=headers, **kwargs
                    ) as retry_resp:
                        if retry_resp.status == 401:
                            raise RainbirdAuthException(
                                "Token expired or unauthorized even after refresh."
                            )
                        if retry_resp.status not in (200, 201, 204):
                            raise RainbirdApiException(
                                f"Request failed with HTTP {retry_resp.status}"
                            )
                        if retry_resp.status == 204:
                            return None
                        return await retry_resp.json()

                if resp.status not in (200, 201, 204):
                    raise RainbirdApiException(
                        f"Request failed with HTTP {resp.status}"
                    )
                if resp.status == 204:
                    return None
                return await resp.json()
        except aiohttp.ClientError as err:
            raise RainbirdConnectionError(
                f"Connection error requesting {path}: {err}"
            ) from err

    async def get_satellites(self) -> list[CloudSatellite]:
        """Retrieve the list of registered satellites/controllers under the user account."""
        data = await self.request(
            "GET",
            "Satellite/GetSatelliteList",
            params={"includeInvisibleToCurrentUser": "false"},
        )
        if not isinstance(data, list):
            raise RainbirdApiException("Expected satellite list response to be a list.")

        satellites = []
        for sat_dict in data:
            try:
                satellites.append(CloudSatellite.from_dict(sat_dict))
            except Exception as err:
                raise RainbirdApiException(
                    f"Error parsing satellite data: {err}. Source: {sat_dict}"
                ) from err

        return satellites

    async def get_satellite(self, satellite_id: int) -> dict[str, Any]:
        """Retrieve details of a specific satellite controller."""
        return await self.request(
            "GET", "Satellite/GetSatellite", params={"satelliteId": satellite_id}
        )

    async def get_station_list(self, satellite_id: int) -> list[dict[str, Any]]:
        """Retrieve the list of stations/zones for a specific satellite."""
        data = await self.request(
            "GET",
            "Station/GetStationListForSatellite",
            params={"satelliteId": satellite_id},
        )
        if not isinstance(data, list):
            raise RainbirdApiException("Expected station list response to be a list.")
        return data

    async def get_run_station_status(self, satellite_id: int) -> list[dict[str, Any]]:
        """Retrieve real-time execution status for all zones on a satellite."""
        data = await self.request(
            "GET",
            "ProgramStep/GetRunStationStatusForSatellite",
            params={"satelliteId": satellite_id},
        )
        if not isinstance(data, list):
            raise RainbirdApiException(
                "Expected run station status response to be a list."
            )
        return data

    async def start_stations(self, station_ids: list[int], seconds: list[int]) -> None:
        """Start manual irrigation on specified stations."""
        await self.request(
            "POST",
            "ManualOps/StartStations",
            json={
                "stationIds": station_ids,
                "seconds": seconds,
                "isGroupStart": False,
            },
        )

    async def advance_stations(self, station_id: int) -> None:
        """Advance or stop a running station."""
        await self.request(
            "POST",
            "ManualOps/AdvanceStations",
            params={"isProgramIndex": "true"},
            json=[{"programId": -1, "stationId": station_id}],
        )

    async def patch_satellite(
        self, satellite_id: int, patch_ops: list[dict[str, Any]]
    ) -> None:
        """Update satellite configuration (e.g. rain delay) via JSON patch."""
        await self.request(
            "PATCH",
            "Satellite/v2/UpdateBatches",
            json={"ids": [satellite_id], "patch": patch_ops},
        )

    async def get_sensor_list(self, satellite_id: int) -> list[dict[str, Any]]:
        """Retrieve the list of sensors connected to a satellite."""
        data = await self.request(
            "GET",
            "Sensor/GetSensorListBySatelliteId",
            params={"satelliteId": satellite_id},
        )
        if not isinstance(data, list):
            raise RainbirdApiException("Expected sensor list response to be a list.")
        return data


class RainbirdCloudTokenProvider(RainbirdTokenProvider):
    """Token provider wrapping AsyncRainbirdCloudClient to manage Bearer tokens."""

    def __init__(self, client: AsyncRainbirdCloudClient) -> None:
        """Initialize RainbirdCloudTokenProvider."""
        self._client = client

    async def async_get_token(self, force_refresh: bool = False) -> str:
        """Return a valid Bearer token, refreshing if necessary or forced."""
        if force_refresh or not self._client.token:
            await self._client.login()
        token = self._client.token
        if not token:
            raise RainbirdAuthException("Could not retrieve a valid Bearer token.")
        return token


class CachingTokenProvider(RainbirdTokenProvider):
    """Token provider that persists the Bearer token in a JSON file."""

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
            os.chmod(self._config_path, 0o600)
        except Exception as err:
            _LOGGER.warning("Failed to save token to cache: %s", err)

    async def async_get_token(self, force_refresh: bool = False) -> str:
        """Return a valid token, reading from environment, cache file, or credentials login."""
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
            raise RainbirdAuthException(
                "No cached token found and credentials (RAINBIRD_CLOUD_USERNAME/RAINBIRD_CLOUD_PASSWORD) are not set."
            )

        _LOGGER.info("Logging in to obtain a new token...")
        token = await self._client.login()
        self._save_token_to_cache(token)
        return token


async def async_authenticate_cloud(
    session: aiohttp.ClientSession,
    username: str,
    password: str,
) -> tuple[str, list[CloudSatellite]]:
    """Helper function to authenticate and fetch satellites in one call."""
    client = AsyncRainbirdCloudClient(session, username, password)
    token = await client.login()
    satellites = await client.get_satellites()
    return token, satellites


class AsyncRainbirdCloudController(RainbirdController):
    """Rainbird cloud controller communicating with the IQ4 REST API."""

    def __init__(self, client: AsyncRainbirdCloudClient, satellite_id: int) -> None:
        """Initialize AsyncRainbirdCloudController."""
        self._client = client
        self._satellite_id = satellite_id
        self._station_id_map: dict[int, int] = {}

    @property
    def supported_features(self) -> set[ControllerFeature]:
        """Return features supported by this controller."""
        return {
            ControllerFeature.ZONE_IRRIGATION,
            ControllerFeature.RAIN_DELAY,
        }

    @property
    def max_zones(self) -> int:
        """Return the maximum number of stations supported."""
        return 32

    @property
    def max_programs(self) -> int:
        """Return the maximum number of programs supported."""
        return 4

    async def _resolve_station_id(self, zone: int) -> int:
        """Map local zone/station number to the cloud station database ID."""
        if zone in self._station_id_map:
            return self._station_id_map[zone]

        stations = await self._client.get_station_list(self._satellite_id)
        for station in stations:
            station_num = station.get("stationNumber") or station.get("number")
            if station_num == zone:
                self._station_id_map[zone] = station["id"]
                return station["id"]

        raise RainbirdApiException(
            f"Zone {zone} not found on the controller satellite."
        )

    async def irrigate_zone(self, zone: int, minutes: int) -> None:
        """Turn on irrigation for a single zone."""
        station_id = await self._resolve_station_id(zone)
        await self._client.start_stations([station_id], [minutes * 60])

    async def stop_irrigation(self) -> None:
        """Turn off all active irrigation zones."""
        running_statuses = await self._client.get_run_station_status(self._satellite_id)
        for status in running_statuses:
            if (
                status.get("isIrrigating")
                or status.get("status") == "running"
                or status.get("state") == "active"
            ):
                station_id = status["stationId"]
                await self._client.advance_stations(station_id)

    async def get_zone_states(self) -> States:
        """Return which zones are currently active."""
        if not self._station_id_map:
            stations = await self._client.get_station_list(self._satellite_id)
            for s in stations:
                num = s.get("stationNumber") or s.get("number")
                if num is not None:
                    self._station_id_map[num] = s["id"]

        reverse_map = {sid: zone for zone, sid in self._station_id_map.items()}

        running_statuses = await self._client.get_run_station_status(self._satellite_id)
        active_zones = set()
        for status in running_statuses:
            if (
                status.get("isIrrigating")
                or status.get("status") == "running"
                or status.get("state") == "active"
            ):
                sid = status["stationId"]
                if sid in reverse_map:
                    active_zones.add(reverse_map[sid])

        mask_bytes = []
        for i in range(0, 32, 8):
            chunk = [bool(z in active_zones) for z in range(i + 1, i + 9)]
            byte_val = sum((1 << j) for j, val in enumerate(chunk) if val)
            mask_bytes.append(f"{byte_val:02X}")
        mask_str = "".join(mask_bytes)
        return States(mask_str)

    async def get_rain_sensor_state(self) -> bool:
        """Return True if the rain sensor is active."""
        sensors = await self._client.get_sensor_list(self._satellite_id)
        for sensor in sensors:
            if sensor.get("type") == "Rain" or "rain" in sensor.get("name", "").lower():
                return bool(sensor.get("state"))
        return False

    async def get_rain_delay(self) -> int:
        """Return the remaining rain delay in days."""
        data = await self._client.get_satellite(self._satellite_id)
        ticks = data.get("rainDelayLong") or 0
        days = int(ticks / (10_000_000 * 3600 * 24))
        return days

    async def set_rain_delay(self, days: int) -> None:
        """Set or clear a rain delay."""
        ticks = days * 24 * 3600 * 10_000_000
        utc_now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        patch_ops = [
            {"op": "replace", "path": "/rainDelayLong", "value": ticks},
            {"op": "replace", "path": "/rainDelayStart", "value": utc_now},
        ]
        await self._client.patch_satellite(self._satellite_id, patch_ops)

    async def get_schedule(self) -> Schedule:
        """Return the controller's irrigation schedule."""
        raise NotImplementedError(
            "Mapping cloud schedule/program is not implemented yet"
        )


def create_cloud_controller(
    session: aiohttp.ClientSession,
    token_provider: RainbirdTokenProvider,
    satellite_id: int,
) -> AsyncRainbirdCloudController:
    """Create an AsyncRainbirdCloudController with the specified token provider."""
    client = AsyncRainbirdCloudClient(session, token_provider=token_provider)
    return AsyncRainbirdCloudController(client, satellite_id)
