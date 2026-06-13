"""Cloud client for rainbird IQ4 service."""

import logging
import re
import urllib.parse
import uuid
import aiohttp

from ..async_client import RainbirdTokenProvider
from ..data import CloudSatellite
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


class AsyncRainbirdCloudClient:
    """Rainbird cloud API client handling OIDC authentication and REST endpoints."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
    ) -> None:
        """Initialize AsyncRainbirdCloudClient."""
        self._session = session
        self._username = username
        self._password = password
        self._token = token
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

    async def login(self) -> str:
        """Emulate OIDC implicit grant login flow to obtain an access token."""
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

        # 1. Fetch the login page to extract CSRF token
        login_url = (
            f"{AUTH_BASE}/Account/Login?ReturnUrl={urllib.parse.quote(return_url)}"
        )

        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://iq4server.rainbird.com",
        }

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

        csrf_token = match.group(1)

        # 2. Submit credentials
        post_url = (
            f"{AUTH_BASE}/Account/Login?ReturnUrl={urllib.parse.quote(return_url)}"
        )
        payload = {
            "Username": self._username,
            "Password": self._password,
            "ReturnUrl": return_url,
            "__RequestVerificationToken": csrf_token,
        }

        try:
            async with self._session.post(
                post_url, data=payload, headers=headers, allow_redirects=False
            ) as resp:
                if resp.status == 200:
                    # Rerendered login page usually means incorrect credentials
                    raise RainbirdAuthException(
                        "Invalid credentials or authentication failure."
                    )
                if resp.status not in (301, 302):
                    raise RainbirdAuthException(
                        f"Unexpected response status submitting credentials: {resp.status}"
                    )
                location = resp.headers.get("Location")
        except aiohttp.ClientError as err:
            raise RainbirdConnectionError(
                f"Connection error submitting credentials: {err}"
            ) from err

        # 3. Follow redirect chain manually to retrieve access token
        access_token_value = None
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
                    access_token_value = token_list[0]
                    break
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

        if not access_token_value:
            raise RainbirdAuthException(
                "Could not retrieve access token from redirect chain."
            )

        self._token = access_token_value
        self._headers["Authorization"] = f"Bearer {self._token}"
        return self._token

    async def get_satellites(self) -> list[CloudSatellite]:
        """Retrieve the list of registered satellites/controllers under the user account."""
        if not self._token:
            raise RainbirdAuthException("No active token. Please call login() first.")

        api_url = f"{API_BASE}/Satellite/GetSatelliteList"
        params = {"includeInvisibleToCurrentUser": "false"}

        try:
            async with self._session.get(
                api_url, headers=self._headers, params=params
            ) as resp:
                if resp.status == 401 and self._username and self._password:
                    # Token might be expired, attempt to re-login once
                    _LOGGER.info("Token expired (401), attempting to refresh token...")
                    await self.login()
                    async with self._session.get(
                        api_url, headers=self._headers, params=params
                    ) as retry_resp:
                        if retry_resp.status == 401:
                            raise RainbirdAuthException(
                                "Token expired or unauthorized even after refresh."
                            )
                        if retry_resp.status != 200:
                            raise RainbirdApiException(
                                f"Failed to fetch satellite list after refresh, HTTP status: {retry_resp.status}"
                            )
                        data = await retry_resp.json()
                else:
                    if resp.status == 401:
                        raise RainbirdAuthException("Token expired or unauthorized.")
                    if resp.status != 200:
                        raise RainbirdApiException(
                            f"Failed to fetch satellite list, HTTP status: {resp.status}"
                        )
                    data = await resp.json()
        except aiohttp.ClientError as err:
            raise RainbirdConnectionError(
                f"Connection error fetching satellite list: {err}"
            ) from err

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
