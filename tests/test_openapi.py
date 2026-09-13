"""Tests for OpenAPI specifications and loader."""

import pytest

from pyrainbird.resources import get_openapi_yaml, load_openapi_spec


def test_load_rb2_raw_spec() -> None:
    """Test loading unbundled raw rb2 OpenAPI spec."""
    spec = load_openapi_spec("rb2", bundle=False)
    assert spec["openapi"] == "3.1.0"
    assert "Communication Device" in spec["info"]["title"]
    assert len(spec["servers"]) >= 2
    assert "BearerAuth" in spec["components"]["securitySchemes"]
    assert "OAuth2AuthorizationCode" in spec["components"]["securitySchemes"]
    assert "OAuth2Implicit" in spec["components"]["securitySchemes"]
    assert "/Satellite/GetSatelliteList" in spec["paths"]
    assert "/connect/token" in spec["paths"]
    assert "/connect/authorize" in spec["paths"]


def test_load_rb2_bundled_spec() -> None:
    """Test loading bundled rb2 OpenAPI spec with resolved refs."""
    spec = load_openapi_spec("rb2", bundle=True)
    assert spec["openapi"] == "3.1.0"
    paths = spec["paths"]

    # Verify Satellites endpoints
    assert "/Satellite/GetSatelliteList" in paths
    assert "get" in paths["/Satellite/GetSatelliteList"]
    sat_list_get = paths["/Satellite/GetSatelliteList"]["get"]
    assert sat_list_get["tags"] == ["Satellites"]
    resp_200 = sat_list_get["responses"]["200"]["content"]["application/json"]["schema"]
    assert resp_200["type"] == "array"
    assert "properties" in resp_200["items"]
    assert "stationCount" in resp_200["items"]["properties"]

    # Verify ManualOps endpoints
    assert "/ManualOps/StartStations" in paths
    start_stations_post = paths["/ManualOps/StartStations"]["post"]
    assert "requestBody" in start_stations_post
    body_schema = start_stations_post["requestBody"]["content"]["application/json"][
        "schema"
    ]
    assert "stationIds" in body_schema["properties"]
    assert "seconds" in body_schema["properties"]

    # Verify Patch endpoints and 96 patch paths
    assert "/Satellite/v2/UpdateBatches" in paths
    patch_op = paths["/Satellite/v2/UpdateBatches"]["patch"]
    patch_schema = patch_op["requestBody"]["content"]["application/json"]["schema"]
    assert "patch" in patch_schema["properties"]
    patch_item = patch_schema["properties"]["patch"]["items"]
    assert "path" in patch_item["properties"]
    patch_path_enum = patch_item["properties"]["path"]["enum"]
    assert "/rainDelayLong" in patch_path_enum
    assert "/useForecast" in patch_path_enum
    assert "/forecastPercentLimit" in patch_path_enum
    assert "/programAdjust" in patch_path_enum
    assert len(patch_path_enum) >= 90

    # Verify Stations, Programs, Reports, Groups, Weather, User
    assert "/Station/GetStationListForSatellite" in paths
    assert "/Program/GetPrograms" in paths
    assert "/ProgramStep/GetProgramSteps" in paths
    assert "/Sensor/GetSensors" in paths
    assert "/Site/GetSites" in paths
    assert "/WeatherData/Forecast" in paths
    assert "/Report/GetEventLogReport" in paths
    assert "/groups" in paths
    assert "/User/GetUser" in paths
    assert "/IoT/CreateIoTGateway" in paths


def test_load_legacy_spec() -> None:
    """Test loading legacy APIService OpenAPI spec."""
    spec = load_openapi_spec("legacy", bundle=True)
    assert spec["openapi"] == "3.1.0"
    assert "Legacy" in spec["info"]["title"]
    paths = spec["paths"]

    # Verify legacy-specific endpoints
    assert "/LandscapeInfo/GetLandscapeInfo" in paths
    assert "/ManualOps/OverrideDial" in paths
    assert "/WeatherData/ET" in paths
    assert "/FlowMonitoring/GetFloWatchActionTypes" in paths
    assert "/Site/DeleteSites_V2" in paths


def test_load_invalid_api() -> None:
    """Test error handling when loading non-existent spec."""
    with pytest.raises(FileNotFoundError, match="OpenAPI spec root not found"):
        load_openapi_spec("non_existent_api")


def test_get_openapi_yaml() -> None:
    """Test generating YAML string from OpenAPI spec."""
    yaml_str = get_openapi_yaml("rb2", bundle=True)
    assert isinstance(yaml_str, str)
    assert "openapi: 3.1.0" in yaml_str
    assert "Communication Device" in yaml_str
    assert "/Satellite/GetSatelliteList" in yaml_str


def test_rb2_auth_and_oauth_endpoints() -> None:
    """Test rb2 authentication, OIDC discovery, and token endpoints."""
    spec = load_openapi_spec("rb2", bundle=True)
    paths = spec["paths"]

    # OIDC discovery
    assert "/.well-known/openid-configuration" in paths
    oidc_get = paths["/.well-known/openid-configuration"]["get"]
    assert oidc_get["tags"] == ["Authentication & OAuth"]
    oidc_resp = oidc_get["responses"]["200"]["content"]["application/json"]["schema"]
    assert "authorization_endpoint" in oidc_resp["properties"]
    assert "token_endpoint" in oidc_resp["properties"]

    # Account Login
    assert "/Account/Login" in paths
    login_post = paths["/Account/Login"]["post"]
    login_req = login_post["requestBody"]["content"][
        "application/x-www-form-urlencoded"
    ]["schema"]
    assert "Username" in login_req["properties"]
    assert "Password" in login_req["properties"]
    assert "__RequestVerificationToken" in login_req["properties"]

    # Connect Authorize
    assert "/connect/authorize" in paths
    auth_get = paths["/connect/authorize"]["get"]
    param_names = [p["name"] for p in auth_get["parameters"]]
    assert "client_id" in param_names
    assert "redirect_uri" in param_names
    assert "response_type" in param_names
    assert "scope" in param_names
    assert "code_challenge" in param_names
    assert "code_challenge_method" in param_names
    assert "prompt" in param_names

    # Connect Token
    assert "/connect/token" in paths
    token_post = paths["/connect/token"]["post"]
    token_req = token_post["requestBody"]["content"][
        "application/x-www-form-urlencoded"
    ]["schema"]
    assert "grant_type" in token_req["properties"]
    assert "client_id" in token_req["properties"]
    assert "client_secret" in token_req["properties"]
    assert "code_verifier" in token_req["properties"]
    assert "refresh_token" in token_req["properties"]
    assert "code" in token_req["properties"]

    # Connect UserInfo, Revocation, Introspection & EndSession
    assert "/connect/userinfo" in paths
    userinfo_schema = paths["/connect/userinfo"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert "company_id" in userinfo_schema["properties"]
    assert "user_id" in userinfo_schema["properties"]

    assert "/connect/revocation" in paths
    assert "/connect/introspect" in paths
    assert "/connect/endsession" in paths
