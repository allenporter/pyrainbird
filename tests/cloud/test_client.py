"""Unit tests for the Rainbird cloud client."""

from collections.abc import Generator
import json
import os
from typing import Any
from unittest import mock

import aiohttp
import asyncio
import pytest
from aiohttp.test_utils import TestClient

from pyrainbird.cloud.client import (
    AsyncRainbirdCloudClient,
    CachingTokenProvider,
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

        if "satellites_payload" in app:
            return aiohttp.web.json_response(app["satellites_payload"])

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

    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        token = await provider.login()

        assert token == "valid_access_token_abc123"
        assert provider.token == "valid_access_token_abc123"
        assert mock_cloud_app["login_attempts"] == 1


async def test_login_invalid_credentials(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test login failure due to invalid credentials."""
    client_session = await aiohttp_client(mock_cloud_app)

    mock_auth_base = "/coreidentityserver"

    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "wrong_password"
        )
        with pytest.raises(RainbirdAuthException, match="Invalid credentials"):
            await provider.login()


async def test_login_missing_csrf(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test login failure when CSRF token cannot be found."""
    mock_cloud_app["fail_csrf"] = True
    client_session = await aiohttp_client(mock_cloud_app)

    mock_auth_base = "/coreidentityserver"

    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        with pytest.raises(
            RainbirdApiException, match="Could not find __RequestVerificationToken"
        ):
            await provider.login()


async def test_login_invalid_redirect_payload(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test login failure when access token is missing in the redirect fragment."""
    mock_cloud_app["invalid_redirect"] = True
    client_session = await aiohttp_client(mock_cloud_app)

    mock_auth_base = "/coreidentityserver"

    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        with pytest.raises(
            RainbirdAuthException,
            match="Reached redirect URI but could not find access_token",
        ):
            await provider.login()


async def test_login_infinite_redirect(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test login failure when maximum redirect limit is hit."""
    mock_cloud_app["infinite_redirect"] = True
    client_session = await aiohttp_client(mock_cloud_app)

    mock_auth_base = "/coreidentityserver"

    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        with pytest.raises(
            RainbirdAuthException, match="Maximum redirect limit reached"
        ):
            await provider.login()


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
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        client = AsyncRainbirdCloudClient(client_session, provider)
        await provider.login()

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
        provider = RainbirdCloudTokenProvider(
            client_session,
            "user@example.com",
            "correct_password",
            token="expired_token",
        )
        client = AsyncRainbirdCloudClient(client_session, provider)

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
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "wrong_password", token="expired_token"
        )
        client = AsyncRainbirdCloudClient(client_session, provider)
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
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )

        assert provider.token is None
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


async def test_caching_token_provider(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
    tmp_path: Any,
) -> None:
    """Test CachingTokenProvider loading, saving, and overriding."""
    client_session = await aiohttp_client(mock_cloud_app)
    mock_auth_base = "/coreidentityserver"

    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        auth_provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        config_file = tmp_path / "rainbird.json"
        provider = CachingTokenProvider(str(config_file), auth_provider)

        # 1. No environment variable, no cache file: triggers login, saves to cache
        assert not config_file.exists()
        token1 = await provider.async_get_token()
        assert token1 == "valid_access_token_abc123"
        assert mock_cloud_app["login_attempts"] == 1
        assert config_file.exists()

        # Verify JSON file content
        with open(config_file, "r") as f:
            content = json.load(f)
        assert content == {"token": "valid_access_token_abc123"}

        # 2. Second request retrieves from in-memory token
        token2 = await provider.async_get_token()
        assert token2 == "valid_access_token_abc123"
        assert mock_cloud_app["login_attempts"] == 1

        # 3. If in-memory is cleared but config file exists, retrieves from config file
        provider._token = None
        token3 = await provider.async_get_token()
        assert token3 == "valid_access_token_abc123"
        assert mock_cloud_app["login_attempts"] == 1

        # 4. Force refresh triggers login and updates config file
        with open(config_file, "w") as f:
            json.dump({"token": "old_expired_token"}, f)

        token4 = await provider.async_get_token(force_refresh=True)
        assert token4 == "valid_access_token_abc123"
        assert mock_cloud_app["login_attempts"] == 2
        with open(config_file, "r") as f:
            content = json.load(f)
        assert content == {"token": "valid_access_token_abc123"}

        # 5. Bypassed via environment variable
        with mock.patch.dict(
            os.environ, {"RAINBIRD_CLOUD_TOKEN": "env_override_token"}
        ):
            token5 = await provider.async_get_token()
            assert token5 == "env_override_token"

        # 6. Missing config file and missing credentials raises RainbirdAuthException
        auth_no_creds = RainbirdCloudTokenProvider(client_session, "", "")
        provider_no_creds = CachingTokenProvider(
            str(tmp_path / "nonexistent.json"), auth_no_creds
        )
        with pytest.raises(
            RainbirdAuthException, match="Username and password are required to log in"
        ):
            await provider_no_creds.async_get_token()


async def test_caching_token_provider_non_blocking(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
    tmp_path: Any,
) -> None:
    """Test that CachingTokenProvider offloads file I/O to an executor."""
    client_session = await aiohttp_client(mock_cloud_app)
    mock_auth_base = "/coreidentityserver"

    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        auth_provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        config_file = tmp_path / "rainbird.json"
        provider = CachingTokenProvider(str(config_file), auth_provider)

        loop = asyncio.get_running_loop()
        with mock.patch.object(
            loop, "run_in_executor", wraps=loop.run_in_executor
        ) as mock_run:
            # First call loads via auth and saves to cache
            token = await provider.async_get_token()
            assert token == "valid_access_token_abc123"
            # Assert _save_token_to_cache_sync was run in the executor
            mock_run.assert_any_call(
                None, provider._save_token_to_cache_sync, "valid_access_token_abc123"
            )

            # Clear token memory cache to force load from file
            provider._token = None
            mock_run.reset_mock()
            token = await provider.async_get_token()
            assert token == "valid_access_token_abc123"
            # Assert _load_token_from_cache_sync was run in the executor
            mock_run.assert_any_call(None, provider._load_token_from_cache_sync)


async def test_caching_token_provider_waf_retry(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
    tmp_path: Any,
) -> None:
    """Test CachingTokenProvider retries when encountering WAF challenges (202)."""
    client_session = await aiohttp_client(mock_cloud_app)
    mock_auth_base = "/coreidentityserver"

    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        auth_provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        config_file = tmp_path / "rainbird.json"
        provider = CachingTokenProvider(str(config_file), auth_provider)

        original_get_csrf = auth_provider._get_csrf_token
        call_count = 0

        async def mock_get_csrf(*args: Any, **kwargs: Any) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                from pyrainbird.exceptions import RainbirdConnectionError

                raise RainbirdConnectionError(
                    "Failed to fetch login page, HTTP status: 202"
                )
            return await original_get_csrf(*args, **kwargs)

        with (
            mock.patch.object(
                auth_provider, "_get_csrf_token", side_effect=mock_get_csrf
            ),
            mock.patch("asyncio.sleep", return_value=None) as mock_sleep,
        ):
            token = await provider.async_get_token()
            assert token == "valid_access_token_abc123"
            assert call_count == 2
            mock_sleep.assert_called_once_with(10.0)

            # Verify token was written to cache file
            with open(config_file, "r") as f:
                content = json.load(f)
            assert content == {"token": "valid_access_token_abc123"}


async def test_caching_token_provider_waf_retry_limit_exceeded(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
    tmp_path: Any,
) -> None:
    """Test CachingTokenProvider stops retrying and raises when WAF retry limit is exceeded."""
    client_session = await aiohttp_client(mock_cloud_app)
    mock_auth_base = "/coreidentityserver"

    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        auth_provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        config_file = tmp_path / "rainbird.json"
        provider = CachingTokenProvider(str(config_file), auth_provider)

        async def mock_get_csrf(*args: Any, **kwargs: Any) -> str:
            from pyrainbird.exceptions import RainbirdConnectionError

            raise RainbirdConnectionError(
                "Failed to fetch login page, HTTP status: 202"
            )

        with (
            mock.patch.object(
                auth_provider, "_get_csrf_token", side_effect=mock_get_csrf
            ),
            mock.patch("asyncio.sleep", return_value=None) as mock_sleep,
        ):
            with pytest.raises(
                RainbirdAuthException,
                match="AWS WAF challenge page detected. Login blocked by WAF",
            ):
                await provider.async_get_token()
            assert mock_sleep.call_count == 3


async def test_login_missing_credentials(aiohttp_client: TestClient) -> None:
    """Test calling login without providing username and password raises RainbirdAuthException."""
    provider = RainbirdCloudTokenProvider(aiohttp_client, "", "")
    with pytest.raises(
        RainbirdAuthException, match="Username and password are required to log in."
    ):
        await provider.login()


async def test_get_csrf_token_non_200_error(aiohttp_client: TestClient) -> None:
    """Test _get_csrf_token when requesting CSRF token returns a non-200 status code."""
    mock_app = aiohttp.web.Application()

    async def get_login(request: aiohttp.web.Request) -> aiohttp.web.Response:
        return aiohttp.web.Response(status=500)

    mock_app.router.add_get("/Account/Login", get_login)

    client_session = await aiohttp_client(mock_app)
    mock_auth_base = ""
    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        with pytest.raises(
            RainbirdApiException, match="Failed to fetch login page, HTTP status: 500"
        ):
            await provider._get_csrf_token("http://return.url", {})


async def test_get_csrf_token_connection_error(aiohttp_client: TestClient) -> None:
    """Test _get_csrf_token when requesting CSRF token triggers a connection error."""
    client_session = await aiohttp_client(aiohttp.web.Application())
    provider = RainbirdCloudTokenProvider(
        client_session, "user@example.com", "correct_password"
    )
    with mock.patch.object(
        client_session, "get", side_effect=aiohttp.ClientError("connection refused")
    ):
        with pytest.raises(
            RainbirdApiException,
            match="Connection error fetching login page: connection refused",
        ):
            await provider._get_csrf_token("http://return.url", {})


def test_parse_login_validation_error_captcha_challenge() -> None:
    """Test _parse_login_validation_error parses HTML containing a captcha challenge."""
    from pyrainbird.cloud.client import _parse_login_validation_error

    html = "<html><body>Please solve this captcha to continue</body></html>"
    assert _parse_login_validation_error(html) == "WAF_CHALLENGE"


def test_parse_login_validation_error_waf_block() -> None:
    """Test _parse_login_validation_error parses HTML containing an AWS WAF block page."""
    from pyrainbird.cloud.client import _parse_login_validation_error

    html = "<html><body>Request blocked by AWS WAF ruleset</body></html>"
    assert _parse_login_validation_error(html) == "WAF_CHALLENGE"


def test_parse_login_validation_error_validation_summary() -> None:
    """Test _parse_login_validation_error parses HTML containing a validation-summary-errors block."""
    from pyrainbird.cloud.client import _parse_login_validation_error

    html = """
    <div class="validation-summary-errors">
      <ul>
        <li>Username not found</li>
      </ul>
    </div>
    """
    assert _parse_login_validation_error(html) == "Username not found"


def test_parse_login_validation_error_field_level() -> None:
    """Test _parse_login_validation_error parses HTML containing field validation errors."""
    from pyrainbird.cloud.client import _parse_login_validation_error

    html = '<span class="field-validation-error">Invalid password format</span>'
    assert _parse_login_validation_error(html) == "Invalid password format"


def test_parse_login_validation_error_text_danger() -> None:
    """Test _parse_login_validation_error parses HTML containing text-danger errors."""
    from pyrainbird.cloud.client import _parse_login_validation_error

    html = '<div class="text-danger">Internal authentication system offline</div>'
    assert (
        _parse_login_validation_error(html) == "Internal authentication system offline"
    )


def test_parse_login_validation_error_none() -> None:
    """Test _parse_login_validation_error returns None when HTML does not contain any errors."""
    from pyrainbird.cloud.client import _parse_login_validation_error

    html = "<html><body>Enter username/password to sign in</body></html>"
    assert _parse_login_validation_error(html) is None


async def test_submit_credentials_waf_captcha_error(aiohttp_client: TestClient) -> None:
    """Test credentials submission returning a 200 containing a WAF captcha challenge raises RainbirdApiException."""
    mock_app = aiohttp.web.Application()

    async def post_login(request: aiohttp.web.Request) -> aiohttp.web.Response:
        return aiohttp.web.Response(
            text="Solve the captcha", content_type="text/html", status=200
        )

    mock_app.router.add_post("/Account/Login", post_login)

    client_session = await aiohttp_client(mock_app)
    mock_auth_base = ""
    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        with pytest.raises(
            RainbirdApiException, match="AWS WAF challenge or captcha page detected"
        ):
            await provider._submit_credentials(
                "http://return.url", "csrf_token_abc", {}
            )


async def test_submit_credentials_validation_error(aiohttp_client: TestClient) -> None:
    """Test credentials submission returning a 200 containing a field error raises RainbirdAuthException."""
    mock_app = aiohttp.web.Application()

    async def post_login(request: aiohttp.web.Request) -> aiohttp.web.Response:
        return aiohttp.web.Response(
            text='<span class="text-danger">Account is locked</span>',
            content_type="text/html",
            status=200,
        )

    mock_app.router.add_post("/Account/Login", post_login)

    client_session = await aiohttp_client(mock_app)
    mock_auth_base = ""
    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        with pytest.raises(
            RainbirdAuthException,
            match="Invalid credentials or authentication failure: Account is locked",
        ):
            await provider._submit_credentials(
                "http://return.url", "csrf_token_abc", {}
            )


async def test_submit_credentials_unknown_validation_error(
    aiohttp_client: TestClient,
) -> None:
    """Test credentials submission returning a 200 containing no parseable error raises general RainbirdAuthException."""
    mock_app = aiohttp.web.Application()

    async def post_login(request: aiohttp.web.Request) -> aiohttp.web.Response:
        return aiohttp.web.Response(
            text="<html><body>Welcome</body></html>",
            content_type="text/html",
            status=200,
        )

    mock_app.router.add_post("/Account/Login", post_login)

    client_session = await aiohttp_client(mock_app)
    mock_auth_base = ""
    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        with pytest.raises(
            RainbirdAuthException,
            match="Invalid credentials or authentication failure.",
        ):
            await provider._submit_credentials(
                "http://return.url", "csrf_token_abc", {}
            )


async def test_submit_credentials_non_redirect_error(
    aiohttp_client: TestClient,
) -> None:
    """Test credentials submission returning an unexpected non-redirect status code raises RainbirdAuthException."""
    mock_app = aiohttp.web.Application()

    async def post_login(request: aiohttp.web.Request) -> aiohttp.web.Response:
        return aiohttp.web.Response(status=500)

    mock_app.router.add_post("/Account/Login", post_login)

    client_session = await aiohttp_client(mock_app)
    mock_auth_base = ""
    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        with pytest.raises(
            RainbirdAuthException,
            match="Unexpected response status submitting credentials: 500",
        ):
            await provider._submit_credentials(
                "http://return.url", "csrf_token_abc", {}
            )


async def test_submit_credentials_missing_location_header_error(
    aiohttp_client: TestClient,
) -> None:
    """Test credentials submission returning a redirect status but no Location header raises RainbirdAuthException."""
    mock_app = aiohttp.web.Application()

    async def post_login(request: aiohttp.web.Request) -> aiohttp.web.Response:
        return aiohttp.web.Response(status=302)

    mock_app.router.add_post("/Account/Login", post_login)

    client_session = await aiohttp_client(mock_app)
    mock_auth_base = ""
    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        with pytest.raises(
            RainbirdAuthException,
            match="No redirect location returned after credentials submission.",
        ):
            await provider._submit_credentials(
                "http://return.url", "csrf_token_abc", {}
            )


async def test_submit_credentials_connection_error(aiohttp_client: TestClient) -> None:
    """Test credentials submission triggering a connection exception raises RainbirdApiException."""
    client_session = await aiohttp_client(aiohttp.web.Application())
    provider = RainbirdCloudTokenProvider(
        client_session, "user@example.com", "correct_password"
    )
    with mock.patch.object(
        client_session, "post", side_effect=aiohttp.ClientError("network failure")
    ):
        with pytest.raises(
            RainbirdApiException,
            match="Connection error submitting credentials: network failure",
        ):
            await provider._submit_credentials(
                "http://return.url", "csrf_token_abc", {}
            )


async def test_follow_redirects_max_limit_error(aiohttp_client: TestClient) -> None:
    """Test following redirects raises RainbirdAuthException when maximum redirect limit is hit."""
    mock_app = aiohttp.web.Application()

    async def get_redirect(request: aiohttp.web.Request) -> aiohttp.web.Response:
        return aiohttp.web.Response(status=302, headers={"Location": "/step1"})

    mock_app.router.add_get("/step1", get_redirect)

    client_session = await aiohttp_client(mock_app)
    mock_auth_base = ""
    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        with pytest.raises(
            RainbirdAuthException, match="Maximum redirect limit reached during login."
        ):
            await provider._follow_redirects("/step1", {})


async def test_follow_redirects_absolute_url_success(
    aiohttp_client: TestClient,
) -> None:
    """Test following redirect chains with absolute URLs in Location headers."""
    mock_app = aiohttp.web.Application()

    async def get_redirect(request: aiohttp.web.Request) -> aiohttp.web.Response:
        return aiohttp.web.Response(
            status=302,
            headers={
                "Location": "https://iq4.rainbird.com/auth.html#access_token=token123"
            },
        )

    mock_app.router.add_get("/step1", get_redirect)

    client_session = await aiohttp_client(mock_app)
    mock_auth_base = ""
    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        token = await provider._follow_redirects("/step1", {})
        assert token == "token123"


async def test_follow_redirects_missing_token_error(aiohttp_client: TestClient) -> None:
    """Test redirect follow flow raises RainbirdAuthException if redirect URI contains no access_token."""
    mock_app = aiohttp.web.Application()

    async def get_redirect(request: aiohttp.web.Request) -> aiohttp.web.Response:
        return aiohttp.web.Response(
            status=302,
            headers={
                "Location": "https://iq4.rainbird.com/auth.html#code=no_token_here"
            },
        )

    mock_app.router.add_get("/step1", get_redirect)

    client_session = await aiohttp_client(mock_app)
    mock_auth_base = ""
    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        with pytest.raises(
            RainbirdAuthException,
            match="Reached redirect URI but could not find access_token in fragment.",
        ):
            await provider._follow_redirects("/step1", {})


async def test_follow_redirects_premature_status_error(
    aiohttp_client: TestClient,
) -> None:
    """Test redirect follow flow raises RainbirdAuthException when redirection status stops at non-redirect code."""
    mock_app = aiohttp.web.Application()

    async def get_redirect(request: aiohttp.web.Request) -> aiohttp.web.Response:
        return aiohttp.web.Response(status=200, headers={"Location": "/step2"})

    mock_app.router.add_get("/step1", get_redirect)

    client_session = await aiohttp_client(mock_app)
    mock_auth_base = ""
    with mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        with pytest.raises(
            RainbirdAuthException,
            match="Redirection stopped prematurely at status 200.",
        ):
            await provider._follow_redirects("/step1", {})


async def test_follow_redirects_connection_error(aiohttp_client: TestClient) -> None:
    """Test redirect follow flow raises RainbirdApiException when network exceptions occur."""
    client_session = await aiohttp_client(aiohttp.web.Application())
    provider = RainbirdCloudTokenProvider(
        client_session, "user@example.com", "correct_password"
    )
    with mock.patch.object(
        client_session, "get", side_effect=aiohttp.ClientError("ssl protocol error")
    ):
        with pytest.raises(
            RainbirdApiException,
            match="Connection error following login redirect: ssl protocol error",
        ):
            await provider._follow_redirects("/step1", {})


async def test_get_satellites_dict_instead_of_list_error(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test get_satellites raises RainbirdApiException when endpoint returns a dictionary instead of a list."""
    mock_cloud_app["satellites_payload"] = {"not": "a_list"}
    client_session = await aiohttp_client(mock_cloud_app)
    mock_auth_base = "/coreidentityserver"
    mock_api_base = "/coreapi/api"

    with (
        mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base),
        mock.patch("pyrainbird.cloud.client.API_BASE", new=mock_api_base),
    ):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        client = AsyncRainbirdCloudClient(client_session, provider)
        await provider.login()
        with pytest.raises(
            RainbirdApiException, match="Expected satellite list response to be a list."
        ):
            await client.get_satellites()


async def test_get_satellites_parsing_error(
    mock_cloud_app: aiohttp.web.Application,
    aiohttp_client: TestClient,
) -> None:
    """Test get_satellites raises RainbirdApiException when record model conversion fails."""
    mock_cloud_app["satellites_payload"] = [
        {"id": "invalid_type_str", "name": "Test Controller"}
    ]
    client_session = await aiohttp_client(mock_cloud_app)
    mock_auth_base = "/coreidentityserver"
    mock_api_base = "/coreapi/api"

    with (
        mock.patch("pyrainbird.cloud.client.AUTH_BASE", new=mock_auth_base),
        mock.patch("pyrainbird.cloud.client.API_BASE", new=mock_api_base),
    ):
        provider = RainbirdCloudTokenProvider(
            client_session, "user@example.com", "correct_password"
        )
        client = AsyncRainbirdCloudClient(client_session, provider)
        await provider.login()
        with pytest.raises(RainbirdApiException, match="Error parsing satellite data"):
            await client.get_satellites()


async def test_token_provider_getter_setter(aiohttp_client: TestClient) -> None:
    """Test the token_provider getter and setter methods."""
    provider1 = RainbirdCloudTokenProvider(
        aiohttp_client, "user@example.com", "correct_password"
    )
    client = AsyncRainbirdCloudClient(aiohttp_client, provider1)
    assert client.token_provider is provider1

    provider2 = RainbirdCloudTokenProvider(
        aiohttp_client, "user2@example.com", "correct_password"
    )
    client.token_provider = provider2
    assert client.token_provider is provider2
