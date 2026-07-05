"""Tests for the Rainbird cloud controller implementation."""

import pytest
from aiohttp import web
from pyrainbird.cloud import (
    create_cloud_controller,
    RainbirdCloudTokenProvider,
    AsyncRainbirdCloudClient,
)

SATELLITE_ID = 12345
PASSWORD = "keepsecret"


@pytest.fixture
async def mock_cloud_api(aiohttp_client) -> tuple:
    """Mock web server for OIDC authentication and REST endpoints."""
    token_attempts = 0
    request_history = []

    async def login_page(request):
        return web.Response(
            text='<input name="__RequestVerificationToken" type="hidden" value="mock-csrf-token" />',
            content_type="text/html",
        )

    async def submit_login(request):
        return web.Response(
            status=302,
            headers={
                "Location": "https://iq4.rainbird.com/auth.html#access_token=mock-access-token"
            },
        )

    async def get_satellites(request):
        request_history.append(("GET", "GetSatelliteList", None))
        nonlocal token_attempts
        auth = request.headers.get("Authorization")
        if auth == "Bearer mock-access-token" and token_attempts == 0:
            token_attempts += 1
            return web.Response(status=401)
        return web.json_response([{"id": SATELLITE_ID, "name": "Test Satellite"}])

    async def get_satellite(request):
        request_history.append(("GET", "GetSatellite", None))
        assert request.query.get("satelliteId") == str(SATELLITE_ID)
        return web.json_response(
            {
                "id": SATELLITE_ID,
                "rainDelayLong": 1728000000000,  # 2 days in .NET ticks
            }
        )

    async def get_station_list(request):
        request_history.append(("GET", "GetStationList", None))
        assert request.query.get("satelliteId") == str(SATELLITE_ID)
        return web.json_response(
            [
                {"id": 111, "stationNumber": 1, "name": "Zone 1"},
                {"id": 222, "stationNumber": 2, "name": "Zone 2"},
            ]
        )

    async def get_run_status(request):
        request_history.append(("GET", "GetRunStationStatus", None))
        assert request.query.get("satelliteId") == str(SATELLITE_ID)
        return web.json_response(
            [
                {"stationId": 111, "isIrrigating": True, "status": "running"},
                {"stationId": 222, "isIrrigating": False, "status": "idle"},
            ]
        )

    async def start_stations(request):
        payload = await request.json()
        request_history.append(("POST", "StartStations", payload))
        return web.json_response({})

    async def advance_stations(request):
        payload = await request.json()
        request_history.append(("POST", "AdvanceStations", payload))
        return web.json_response({})

    async def update_batches(request):
        payload = await request.json()
        request_history.append(("PATCH", "UpdateBatches", payload))
        return web.json_response({})

    async def get_sensors(request):
        request_history.append(("GET", "GetSensorList", None))
        return web.json_response(
            [{"id": 555, "type": "Rain", "name": "Rain Sensor", "state": True}]
        )

    app = web.Application()
    app.router.add_get("/coreidentityserver/Account/Login", login_page)
    app.router.add_post("/coreidentityserver/Account/Login", submit_login)
    app.router.add_get("/coreapi/api/Satellite/GetSatelliteList", get_satellites)
    app.router.add_get("/coreapi/api/Satellite/GetSatellite", get_satellite)
    app.router.add_get(
        "/coreapi/api/Station/GetStationListForSatellite", get_station_list
    )
    app.router.add_get(
        "/coreapi/api/ProgramStep/GetRunStationStatusForSatellite", get_run_status
    )
    app.router.add_post("/coreapi/api/ManualOps/StartStations", start_stations)
    app.router.add_post("/coreapi/api/ManualOps/AdvanceStations", advance_stations)
    app.router.add_patch("/coreapi/api/Satellite/v2/UpdateBatches", update_batches)
    app.router.add_get("/coreapi/api/Sensor/GetSensorListBySatelliteId", get_sensors)

    client = await aiohttp_client(app)
    return client, request_history


@pytest.mark.asyncio
async def test_cloud_controller_operations(mock_cloud_api, monkeypatch) -> None:
    """Test all core features of the cloud controller client with auth mocking."""
    client_app, history = mock_cloud_api

    import pyrainbird.cloud.client

    monkeypatch.setattr(
        pyrainbird.cloud.client,
        "AUTH_BASE",
        str(client_app.make_url("/coreidentityserver")),
    )
    monkeypatch.setattr(
        pyrainbird.cloud.client, "API_BASE", str(client_app.make_url("/coreapi/api"))
    )

    login_calls = 0

    async def mock_login(self, max_retries=3):
        nonlocal login_calls
        if login_calls == 0:
            login_calls += 1
            self._token = "mock-access-token"
        else:
            self._token = "mock-access-token-refreshed"
        self._headers["Authorization"] = f"Bearer {self._token}"
        return self._token

    monkeypatch.setattr(AsyncRainbirdCloudClient, "login", mock_login)

    cloud_client = AsyncRainbirdCloudClient(
        client_app.session, "user@example.com", PASSWORD
    )
    token_provider = RainbirdCloudTokenProvider(cloud_client)

    controller = create_cloud_controller(
        client_app.session, token_provider, SATELLITE_ID
    )

    # 1. Verify basic properties
    assert controller.max_zones == 32
    assert controller.max_programs == 4
    assert len(controller.supported_features) == 2

    # 2. Test get_rain_delay (Should return 2 days from ticks: 1728000000000)
    delay = await controller.get_rain_delay()
    assert delay == 2

    # 3. Test set_rain_delay (Should patch ticks: 5 * 24 * 3600 * 10,000,000)
    await controller.set_rain_delay(5)
    assert any(
        op[0] == "PATCH"
        and op[1] == "UpdateBatches"
        and op[2]["patch"][0]["value"] == 4320000000000
        for op in history
    )

    # 4. Test irrigate_zone
    await controller.irrigate_zone(zone=1, minutes=10)
    assert any(
        op[0] == "POST"
        and op[1] == "StartStations"
        and op[2]["stationIds"] == [111]
        and op[2]["seconds"] == [600]
        for op in history
    )

    # 5. Test stop_irrigation
    await controller.stop_irrigation()
    assert any(
        op[0] == "POST"
        and op[1] == "AdvanceStations"
        and op[2] == [{"programId": -1, "stationId": 111}]
        for op in history
    )

    # 6. Test get_zone_states
    zone_states = await controller.get_zone_states()
    assert zone_states.active(1) is True
    assert zone_states.active(2) is False

    # 7. Test get_rain_sensor_state
    rain_sensor = await controller.get_rain_sensor_state()
    assert rain_sensor is True

    # 8. Test get_schedule raises NotImplementedError
    with pytest.raises(NotImplementedError):
        await controller.get_schedule()
