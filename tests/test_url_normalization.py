import aiohttp

from pyrainbird.async_client import AsyncRainbirdClient


async def test_async_rainbird_client_url_normalization_https() -> None:
    async with aiohttp.ClientSession() as session:
        client = AsyncRainbirdClient(session, "https://example.com", "password")
        assert client._url == "https://example.com/stick"

        client = AsyncRainbirdClient(session, "https://example.com/", "password")
        assert client._url == "https://example.com/stick"

        client = AsyncRainbirdClient(session, "https://example.com/stick", "password")
        assert client._url == "https://example.com/stick"


async def test_async_rainbird_client_url_normalization_http() -> None:
    async with aiohttp.ClientSession() as session:
        client = AsyncRainbirdClient(session, "http://example.com", "password")
        assert client._url == "http://example.com/stick"

        client = AsyncRainbirdClient(session, "http://example.com/", "password")
        assert client._url == "http://example.com/stick"

        client = AsyncRainbirdClient(session, "http://example.com/stick", "password")
        assert client._url == "http://example.com/stick"


async def test_async_rainbird_client_url_normalization_no_scheme() -> None:
    async with aiohttp.ClientSession() as session:
        client = AsyncRainbirdClient(session, "example.com", "password")
        assert client._url == "http://example.com/stick"

        client = AsyncRainbirdClient(session, "example.com/", "password")
        assert client._url == "http://example.com/stick"

