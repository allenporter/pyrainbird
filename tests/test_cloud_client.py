"""Unit tests for the Rainbird cloud client."""

from collections.abc import Generator
from unittest import mock

import aiohttp
import pytest
from aiohttp.test_utils import TestClient

from pyrainbird.cloud.client import (
    AsyncRainbirdCloudClient,
    RainbirdCloudTokenProvider,
    async_authenticate_cloud,
)
from pyrainbird.data import CloudSatellite
from pyrainbird.exceptions import (
    RainbirdApiException,
    RainbirdAuthException,
)

# Mocked constants/URLs to override for local testing server
MOCK_REDIRECT_URI = "https://iq4.rainbird.com/auth.html"


@pytest.fixture
def mock_cloud_app() -> aiohttp.web.Application:
    """Fixture to create the mock cloud web app."""
    app = aiohttp.web.Application()
    app["fail_csrf"] = False
    app["fail_credentials"] = False
    app["invalid_redirect"] = False
    app["infinite_redirect"] = False
    app["login_attempts"] = 0
    app["get_satellites_attempts"] = 0
    app["token_valid"] = True

    async def get_login(request: aiohttp.web.Request) -> aiohttp.web.Response:
        if app["fail_csrf"]:
            html = "<html><body>No CSRF token here</body></html>"
        else:
            html = """
            <html>
            <body>
            <form>
            <input name="__RequestVerificationToken" type="hidden" value="mock_csrf_token_12345" />
            </form>
            </body>
            </html>
            """
        return aiohttp.web.Response(text=html, content_type="text/html")

    async def post_login(request: aiohttp.web.Request) -> aiohttp.web.Response:
        app["login_attempts"] += 1
        data = await request.post()
        if app["fail_credentials"] or data.get("Password") != "correct_password":
            # Re-render login page (status 200) indicating failure
            return aiohttp.web.Response(
                text="Invalid username or password",
                content_type="text/html",
                status=200,
            )

        # Successful login makes token valid
        app["token_valid"] = True

        if app["infinite_redirect"]:
            return aiohttp.web.Response(
                status=302,
                headers={"Location": "/coreidentityserver/connect/authorize/callback"},
            )

        # Redirect to callback URL
        return_url = request.query.get("ReturnUrl", "")
        return aiohttp.web.Response(status=302, headers={"Location": return_url})

    async def get_callback(request: aiohttp.web.Request) -> aiohttp.web.Response:
        if app["infinite_redirect"]:
            return aiohttp.web.Response(
                status=302,
                headers={"Location": "/coreidentityserver/connect/authorize/callback"},
            )
        if app["invalid_redirect"]:
            location = f"{MOCK_REDIRECT_URI}#error=some_error"
        else:
            location = f"{MOCK_REDIRECT_URI}#access_token=valid_access_token_abc123&token_type=Bearer"
        return aiohttp.web.Response(status=302, headers={"Location": location})

    async def get_satellite_list(request: aiohttp.web.Request) -> aiohttp.web.Response:
        app["get_satellites_attempts"] += 1
        auth_header = request.headers.get("Authorization")
        if not app["token_valid"] or auth_header != "Bearer valid_access_token_abc123":
            return aiohttp.web.json_response({"error": "unauthorized"}, status=401)

        satellites = [
            {
                "id": 527302,
                "name": "Test Controller",
                "type": 69,
                "siteId": 657314,
                "siteName": "Woodgreen",
                "deviceUUID": "7b1ad1ef-91df-4e50-9004-269c139c681c",
                "stationCount": 4,
                "satelliteEnabled": True,
                "description": "This is a test controller",
            }
        ]
        return aiohttp.web.json_response(satellites)

    app.router.add_get("/coreidentityserver/Account/Login", get_login)
    app.router.add_post("/coreidentityserver/Account/Login", post_login)
    app.router.add_get("/coreidentityserver/connect/authorize/callback", get_callback)
    app.router.add_get("/coreapi/api/Satellite/GetSatelliteList", get_satellite_list)

    return app


@pytest.fixture
def mock_cloud_client(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> Generator[TestClient, None, None]:
    """Fixture to run the mock cloud server."""
    yield mock_cloud_app


async def test_login_success(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test successful cloud login flow."""
    client_session = await aiohttp_client(mock_cloud_app)

    mock_auth_base = "/coreidentityserver"
    mock_api_base = "/coreapi/api"

    with (
        mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base),
        mock.patch("pyrainbird.cloud.client.API_BASE", new=mock_api_base),
    ):
        client = AsyncRainbirdCloudClient(
            client_session, "user@example.com", "correct_password"
        )
        token = await client.login()

        assert token == "valid_access_token_abc123"
        assert client.token == "valid_access_token_abc123"
        assert mock_cloud_app["login_attempts"] == 1


async def test_login_invalid_credentials(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test login failure due to invalid credentials."""
    client_session = await aiohttp_client(mock_cloud_app)

    mock_auth_base = "/coreidentityserver"

    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        client = AsyncRainbirdCloudClient(
            client_session, "user@example.com", "wrong_password"
        )
        with pytest.raises(RainbirdAuthException, match="Invalid credentials"):
            await client.login()


async def test_login_missing_csrf(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test login failure when CSRF token cannot be found."""
    mock_cloud_app["fail_csrf"] = True
    client_session = await aiohttp_client(mock_cloud_app)

    mock_auth_base = "/coreidentityserver"

    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        client = AsyncRainbirdCloudClient(
            client_session, "user@example.com", "correct_password"
        )
        with pytest.raises(
            RainbirdApiException, match="Could not find __RequestVerificationToken"
        ):
            await client.login()


async def test_login_invalid_redirect_payload(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test login failure when access token is missing in the redirect fragment."""
    mock_cloud_app["invalid_redirect"] = True
    client_session = await aiohttp_client(mock_cloud_app)

    mock_auth_base = "/coreidentityserver"

    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        client = AsyncRainbirdCloudClient(
            client_session, "user@example.com", "correct_password"
        )
        with pytest.raises(RainbirdAuthException, match="could not find access_token"):
            await client.login()


async def test_login_infinite_redirect(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test login failure when maximum redirect limit is hit."""
    mock_cloud_app["infinite_redirect"] = True
    client_session = await aiohttp_client(mock_cloud_app)

    mock_auth_base = "/coreidentityserver"

    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        client = AsyncRainbirdCloudClient(
            client_session, "user@example.com", "correct_password"
        )
        with pytest.raises(
            RainbirdAuthException, match="Maximum redirect limit reached"
        ):
            await client.login()


async def test_get_satellites_success(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test fetching satellites successfully with a valid token."""
    client_session = await aiohttp_client(mock_cloud_app)

    mock_auth_base = "/coreidentityserver"
    mock_api_base = "/coreapi/api"

    with (
        mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base),
        mock.patch("pyrainbird.cloud.client.API_BASE", new=mock_api_base),
    ):
        client = AsyncRainbirdCloudClient(
            client_session, "user@example.com", "correct_password"
        )
        # Login first to get token
        await client.login()

        satellites = await client.get_satellites()
        assert len(satellites) == 1
        sat = satellites[0]
        assert isinstance(sat, CloudSatellite)
        assert sat.id == 527302
        assert sat.name == "Test Controller"
        assert sat.type == 69
        assert sat.site_id == 657314
        assert sat.site_name == "Woodgreen"
        assert sat.device_uuid == "7b1ad1ef-91df-4e50-9004-269c139c681c"
        assert sat.station_count == 4
        assert sat.satellite_enabled is True
        assert sat.description == "This is a test controller"


async def test_get_satellites_auto_refresh_on_401(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test that get_satellites automatically logs back in once if a 401 is encountered."""
    client_session = await aiohttp_client(mock_cloud_app)

    mock_auth_base = "/coreidentityserver"
    mock_api_base = "/coreapi/api"

    with (
        mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base),
        mock.patch("pyrainbird.cloud.client.API_BASE", new=mock_api_base),
    ):
        # Initialize client with credentials and an expired/invalid token
        client = AsyncRainbirdCloudClient(
            client_session,
            "user@example.com",
            "correct_password",
            token="expired_token",
        )

        mock_cloud_app["token_valid"] = False  # Initially unauthorized

        satellites = await client.get_satellites()
        assert len(satellites) == 1
        assert satellites[0].id == 527302
        assert mock_cloud_app["login_attempts"] == 1
        # 1st try (expired_token -> 401) + 2nd try (valid_access_token_abc123 -> 200)
        assert mock_cloud_app["get_satellites_attempts"] == 2


async def test_get_satellites_raises_unauthorized_if_retry_fails(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test that get_satellites raises RainbirdAuthException if retry also fails with 401."""
    client_session = await aiohttp_client(mock_cloud_app)

    mock_auth_base = "/coreidentityserver"
    mock_api_base = "/coreapi/api"

    with (
        mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base),
        mock.patch("pyrainbird.cloud.client.API_BASE", new=mock_api_base),
    ):
        # Initialize client with wrong password so refresh also fails
        client = AsyncRainbirdCloudClient(
            client_session, "user@example.com", "wrong_password", token="expired_token"
        )
        mock_cloud_app["token_valid"] = False

        with pytest.raises(RainbirdAuthException, match="Invalid credentials"):
            await client.get_satellites()


async def test_cloud_token_provider(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test RainbirdCloudTokenProvider caching and force refresh."""
    client_session = await aiohttp_client(mock_cloud_app)

    mock_auth_base = "/coreidentityserver"

    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        client = AsyncRainbirdCloudClient(
            client_session, "user@example.com", "correct_password"
        )
        provider = RainbirdCloudTokenProvider(client)

        assert client.token is None
        # 1. Fetching first time triggers login
        token1 = await provider.async_get_token()
        assert token1 == "valid_access_token_abc123"
        assert mock_cloud_app["login_attempts"] == 1

        # 2. Fetching second time returns cached token
        token2 = await provider.async_get_token()
        assert token2 == "valid_access_token_abc123"
        assert mock_cloud_app["login_attempts"] == 1

        # 3. Force refresh triggers login again
        token3 = await provider.async_get_token(force_refresh=True)
        assert token3 == "valid_access_token_abc123"
        assert mock_cloud_app["login_attempts"] == 2


async def test_async_authenticate_cloud_helper(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test async_authenticate_cloud helper function."""
    client_session = await aiohttp_client(mock_cloud_app)

    mock_auth_base = "/coreidentityserver"
    mock_api_base = "/coreapi/api"

    with (
        mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base),
        mock.patch("pyrainbird.cloud.client.API_BASE", new=mock_api_base),
    ):
        token, satellites = await async_authenticate_cloud(
            client_session, "user@example.com", "correct_password"
        )

        assert token == "valid_access_token_abc123"
        assert len(satellites) == 1
        assert satellites[0].id == 527302
        assert mock_cloud_app["login_attempts"] == 1
        assert mock_cloud_app["get_satellites_attempts"] == 1
