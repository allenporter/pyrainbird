"""Tests for the Rainbird cloud controller implementation."""

import datetime
import pytest
from aiohttp import web
from pyrainbird.const import DayOfWeek
from pyrainbird.async_client import ControllerFeature
from pyrainbird.cloud import (
    create_cloud_controller,
    RainbirdCloudTokenProvider,
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
                "siteId": 657314,
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

    async def get_programs(request):
        request_history.append(("GET", "GetProgramList", None))
        assert request.query.get("satelliteId") == str(SATELLITE_ID)
        return web.json_response(
            [
                {
                    "id": 999,
                    "name": "Program A",
                    "shortName": "PGM A",
                    "isEnabled": True,
                    "startTime": "2026-06-13T08:00:00Z",
                    "weekDays": "0111110",
                    "programAdjust": 100,
                }
            ]
        )

    async def get_programs_assigned(request):
        request_history.append(
            ("GET", "GetProgramsAssignedAndRunTimeBySatelliteId", None)
        )
        assert request.query.get("satelliteId") == str(SATELLITE_ID)
        return web.json_response(
            [
                {
                    "stationId": 111,
                    "runtimeProgramAssignedList": [
                        {
                            "programId": 999,
                            "programShortName": "PGM A",
                            "baseRunTime": "00:15:00",
                            "adjustedRunTime": "00:15:00",
                        }
                    ],
                }
            ]
        )

    async def stop_all_irrigation(request):
        payload = await request.json()
        request_history.append(("POST", "StopAllIrrigation", payload))
        return web.json_response({})

    async def get_seasonal_adjust(request):
        request_history.append(("GET", "GetSeasonalAdjustForSite", None))
        assert request.query.get("siteId") == "657314"
        return web.json_response(
            {
                "id": 657232,
                "siteId": 657314,
                "seasonalAdjustPct": 100,
                "adjustTypeId": 3,
                "janAdjust": 100,
                "febAdjust": 100,
                "marAdjust": 100,
                "aprAdjust": 100,
                "mayAdjust": 100,
                "junAdjust": 100,
                "julAdjust": 100,
                "augAdjust": 100,
                "sepAdjust": 100,
                "octAdjust": 100,
                "novAdjust": 100,
                "decAdjust": 100,
            }
        )

    async def get_flow_elements(request):
        request_history.append(("GET", "GetFlowElements", None))
        assert request.query.get("satelliteId") == str(SATELLITE_ID)
        return web.json_response(
            [
                {
                    "id": 636362,
                    "name": "FloZone 1",
                    "flowRate": 12.5,
                    "hasFlowAlarm": False,
                    "flowCapacity": 50.0,
                    "satelliteId": SATELLITE_ID,
                }
            ]
        )

    async def get_firmware_versions(request):
        request_history.append(("GET", "GetSatelliteFirmwareVersions", None))
        assert request.query.get("satelliteId") == str(SATELLITE_ID)
        return web.json_response(
            {
                "current": {
                    "id": SATELLITE_ID,
                    "type": 69,
                    "version": "1.0",
                    "siteID": 657314,
                    "companyID": 315876,
                    "bootloaderVersion": "0.0",
                    "cicType": 0,
                    "cicVersion": "0.0",
                    "hasMrm": False,
                }
            }
        )

    async def is_connected(request):
        request_history.append(("GET", "isConnected", None))
        assert request.query.get("satelliteId") == str(SATELLITE_ID)
        return web.json_response({"satellites": [SATELLITE_ID]})

    async def start_programs(request):
        payload = await request.json()
        request_history.append(("POST", "StartPrograms", payload))
        return web.json_response({})

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
    app.router.add_get("/coreapi/api/Program/GetProgramList", get_programs)
    app.router.add_get(
        "/coreapi/api/ProgramStep/GetProgramsAssignedAndRunTimeBySatelliteId",
        get_programs_assigned,
    )
    app.router.add_post("/coreapi/api/Satellite/StopAllIrrigation", stop_all_irrigation)
    app.router.add_get(
        "/coreapi/api/SeasonalAdjust/GetSeasonalAdjustForSite", get_seasonal_adjust
    )
    app.router.add_get("/coreapi/api/FlowElement/GetFlowElements", get_flow_elements)
    app.router.add_get(
        "/coreapi/api/ManualOps/GetSatelliteFirmwareVersions", get_firmware_versions
    )
    app.router.add_get("/coreapi/api/Satellite/isConnected", is_connected)
    app.router.add_post("/coreapi/api/ManualOps/StartPrograms", start_programs)

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
        return self._token

    monkeypatch.setattr(RainbirdCloudTokenProvider, "login", mock_login)

    token_provider = RainbirdCloudTokenProvider(
        client_app.session, "user@example.com", PASSWORD
    )
    controller = create_cloud_controller(
        client_app.session, SATELLITE_ID, token_provider=token_provider
    )

    # 1. Verify basic properties
    assert controller.max_zones == 32
    assert controller.max_programs == 4
    assert len(controller.supported_features) == 3
    assert ControllerFeature.SEASONAL_ADJUST in controller.supported_features

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
        op[0] == "POST" and op[1] == "StopAllIrrigation" and op[2] == [SATELLITE_ID]
        for op in history
    )

    # 6. Test get_zone_states
    zone_states = await controller.get_zone_states()
    assert zone_states.active(1) is True
    assert zone_states.active(2) is False

    # 7. Test get_rain_sensor_state
    rain_sensor = await controller.get_rain_sensor_state()
    assert rain_sensor is True

    # 8. Test get_schedule
    schedule = await controller.get_schedule()
    assert schedule is not None
    assert schedule.controller_info.rain_delay == 2
    assert schedule.controller_info.rain_sensor is True
    assert len(schedule.programs) == 1

    prog = schedule.programs[0]
    assert prog.program == 0
    assert prog.starts == [datetime.time(8, 0)]
    assert prog.days_of_week == {
        DayOfWeek.MONDAY,
        DayOfWeek.TUESDAY,
        DayOfWeek.WEDNESDAY,
        DayOfWeek.THURSDAY,
        DayOfWeek.FRIDAY,
    }
    assert len(prog.durations) == 1
    assert prog.durations[0].zone == 1
    assert prog.durations[0].duration == datetime.timedelta(minutes=15)

    # 9. Test get_seasonal_adjust
    sa = await controller.get_seasonal_adjust()
    assert sa.seasonal_adjust_pct == 100
    assert sa.site_id == 657314
    assert sa.jan_adjust == 100

    # 10. Test get_flow_elements
    flow_elements = await controller.get_flow_elements()
    assert len(flow_elements) == 1
    assert flow_elements[0].name == "FloZone 1"
    assert flow_elements[0].flow_rate == 12.5

    # 11. Test get_firmware_versions
    fw = await controller.get_firmware_versions()
    assert fw.current.version == "1.0"
    assert fw.current.id == SATELLITE_ID

    # 12. Test is_connected
    connected = await controller.is_connected()
    assert connected is True

    # 13. Test start_programs
    await controller.start_programs([999])
    assert any(
        op[0] == "POST" and op[1] == "StartPrograms" and op[2] == [999]
        for op in history
    )
