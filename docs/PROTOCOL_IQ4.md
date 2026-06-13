# Rain Bird IQ4 Cloud API Specification

This document details the **Rain Bird IQ4 REST API (Rain Bird 2.0 app)** protocol. Modern Rain Bird controller firmware upgrades migrate devices from the local JSON-RPC / LNK client API to this cloud-based platform.

This specification is based on the custom component implementation by [@davidsuarez82](https://github.com/davidsuarez82) in [davidsuarez82/rainbird_iq4](https://github.com/davidsuarez82/rainbird_iq4).

---

## 1. Authentication Infrastructure

The IQ4 cloud platform uses OAuth 2.0 / OpenID Connect (OIDC) JWT token-based authentication.

- **Authentication Base URL:** `https://iq4server.rainbird.com/coreidentityserver`
- **API Base URL:** `https://iq4server.rainbird.com/coreapi/api`
- **OAuth Client ID:** Any dynamically generated random UUID (e.g., `C5A6F324-3CD3-4B22-9F78-B4835BA55D25`). The official app generates a UUID on initial setup using `UUID.randomUUID().toString()` and stores it as the `APP_CLIENT_ID` in preferences.
- **Redirect URI:** `https://iq4.rainbird.com/auth.html`

### Authentication Flow (Browser Emulation / Bypass)

AWS WAF protects the authentication endpoints, typically requiring clients to handle cookies and headers properly (e.g., using `curl_cffi` to impersonate browser fingerprints).

1. **Initiate Authorization Request:**
   Generate a random hexadecimal `state` and `nonce` (8 bytes each). Build the Return URL:
   ```
   /coreidentityserver/connect/authorize/callback?client_id=C5A6F324-3CD3-4B22-9F78-B4835BA55D25&redirect_uri=https%3A%2F%2Fiq4.rainbird.com%2Fauth.html&response_type=id_token%20token&scope=coreAPI.read%20coreAPI.write%20openid%20profile&state=<STATE>&nonce=<NONCE>
   ```

2. **Retrieve Login Page & CSRF Token:**
   Perform a GET request to:
   ```
   https://iq4server.rainbird.com/coreidentityserver/Account/Login?ReturnUrl=<URL_ENCODED_RETURN_URL>
   ```
   Extract the verification token value from the HTML response:
   ```html
   <input name="__RequestVerificationToken" type="hidden" value="<CSRF_TOKEN>" />
   ```

3. **Submit Credentials:**
   Perform a POST request to the same Login URL with the following form-encoded payload:
   - `Username`: `<User Email>`
   - `Password`: `<User Password>`
   - `ReturnUrl`: `<UNENCODED_RETURN_URL>`
   - `__RequestVerificationToken`: `<CSRF_TOKEN>`

4. **Extract JWT Access Token:**
   Upon successful authentication, the server redirects back to the redirect URI with a hash fragment containing the JWT token. Parse the redirection URL to extract `access_token` and `id_token`:
   ```
   https://iq4.rainbird.com/auth.html#id_token=<JWT>&access_token=<JWT_ACCESS_TOKEN>&token_type=Bearer&expires_in=3600&state=<STATE>&session_state=<SESSION_STATE>
   ```

5. **API Header Authorization:**
   Add the retrieved access token to all subsequent API requests:
   ```http
   Authorization: Bearer <JWT_ACCESS_TOKEN>
   Accept: application/json
   ```

---

## 2. API Endpoints Reference

All API calls are relative to the API Base URL: `https://iq4server.rainbird.com/coreapi/api/`.

### 2.1 Satellites (Controllers)

#### Get Satellite Details
- **HTTP Method:** `GET`
- **Path:** `Satellite/GetSatellite`
- **Query Parameters:**
  - `satelliteId` (integer)
- **Description:** Returns the details of a specific controller.

#### Get Connection Status
- **HTTP Method:** `GET`
- **Path:** `Satellite/isConnected`
- **Query Parameters:**
  - `satelliteIds` (integer or list of integers)
- **Description:** Returns whether the controller is actively connected to the cloud service.

#### Update Satellite Configuration (Rain Delay / Forecast)
- **HTTP Method:** `PATCH`
- **Path:** `Satellite/v2/UpdateBatches`
- **Headers:** `Content-Type: application/json`
- **JSON Request Body:**
  ```json
  {
    "ids": [<SATELLITE_ID>],
    "patch": [
      { "op": "replace", "path": "/<FIELD>", "value": <VALUE> }
    ]
  }
  ```
- **Common Fields to Patch:**
  - `/rainDelayLong`: Rain delay duration in .NET ticks (1 tick = 100ns; e.g. `days * 24 * 3600 * 10,000,000`).
  - `/rainDelayStart`: ISO-8601 UTC timestamp of delay start (e.g., `2026-06-13T17:20:00Z`).
  - `/useForecast`: Boolean to enable/disable forecast-based rain delay.
  - `/forecastPercentLimit`: Integer rain probability threshold (0-100).
  - `/forecastInchesLimit`: Float precipitation depth threshold (in inches).
  - `/forecastDelayDays`: Integer delay days.

---

### 2.2 Programs

#### Get Program List
- **HTTP Method:** `GET`
- **Path:** `Program/GetProgramList`
- **Query Parameters:**
  - `satelliteId` (integer)
- **Description:** Returns all irrigation programs (e.g., A, B, C, D) configured on the satellite.

#### Update Program Configuration (Seasonal Adjust)
- **HTTP Method:** `PATCH`
- **Path:** `Program/UpdateBatches`
- **Headers:** `Content-Type: application/json`
- **JSON Request Body:**
  ```json
  {
    "ids": [<PROGRAM_ID>],
    "patch": [
      { "op": "replace", "path": "/<FIELD>", "value": <VALUE> }
    ]
  }
  ```
- **Common Fields to Patch:**
  - `/etAdjustType`: Weather adjust method integer (e.g., `6` for manual, `7` for automatic seasonal adjust).
  - `/programAdjust`: Seasonal adjustment percentage integer (e.g., `5` to `200` percent).

---

### 2.3 Stations (Zones)

#### Get Station List
- **HTTP Method:** `GET`
- **Path:** `Station/GetStationListForSatellite`
- **Query Parameters:**
  - `satelliteId` (integer)
- **Description:** Returns metadata for all stations/zones attached to the controller.

#### Get Station Run Status
- **HTTP Method:** `GET`
- **Path:** `ProgramStep/GetRunStationStatusForSatellite`
- **Query Parameters:**
  - `satelliteId` (integer)
- **Description:** Returns real-time execution status for all zones (e.g., running, idle, paused).

#### Get Programs Assigned Runtime
- **HTTP Method:** `GET`
- **Path:** `ProgramStep/GetProgramsAssignedAndRunTimeBySatelliteId`
- **Query Parameters:**
  - `satelliteId` (integer)
- **Description:** Returns configured runtimes per station mapped to programs.

---

### 2.4 Manual Operations

#### Start Station Manually
- **HTTP Method:** `POST`
- **Path:** `ManualOps/StartStations`
- **Headers:** `Content-Type: application/json`
- **JSON Request Body:**
  ```json
  {
    "stationIds": [<STATION_ID>],
    "seconds": [<RUN_DURATION_SECONDS>],
    "isGroupStart": false
  }
  ```

#### Stop / Advance Station
- **HTTP Method:** `POST`
- **Path:** `ManualOps/AdvanceStations`
- **Query Parameters:**
  - `isProgramIndex`: `true`
- **Headers:** `Content-Type: application/json`
- **JSON Request Body:**
  ```json
  [
    {
      "programId": -1,
      "stationId": <STATION_ID>
    }
  ]
  ```

---

### 2.5 Sensors & Flow Elements

#### Get Sensor List
- **HTTP Method:** `GET`
- **Path:** `Sensor/GetSensorListBySatelliteId`
- **Query Parameters:**
  - `satelliteId` (integer)
- **Description:** Lists rain, wind, or soil sensors hooked to the controller.

#### Get Flow Zones/Elements
- **HTTP Method:** `GET`
- **Path:** `FlowElement/GetFlowElements`
- **Query Parameters:**
  - `parentId`: (empty string or root identifier)
  - `satelliteId` (integer)
  - `includeHiddenFlowZones`: `false`

#### Get Flow Monitoring Config
- **HTTP Method:** `GET`
- **Path:** `FlowMonitoring/GetFlowMonitoringBySatelliteId`
- **Query Parameters:**
  - `satelliteId` (integer)

---

### 2.6 System Logs & Alerts

#### Get Company Status (Alerts Summary)
- **HTTP Method:** `GET`
- **Path:** `Company/GetCompanyStatusCore`
- **Query Parameters:**
  - `companyId` (integer)
- **Description:** Retrieves high-level warning and alarm counts for the user account's parent company.

#### Get Event Logs
- **HTTP Method:** `POST`
- **Path:** `EventLog/GetEventLogsBySatelliteIds_V2`
- **Query Parameters:**
  - `startTime` (string: `YYYY-MM-DDTHH:MM:SS`)
  - `endTime` (string: `YYYY-MM-DDTHH:MM:SS`)
  - `types`: `15`
  - `includeAcknowledgedAlarms`: `true`
  - `includeAcknowledgedWarnings`: `true`
- **Headers:** `Content-Type: application/json`
- **JSON Request Body:**
  ```json
  [<SATELLITE_ID>]
  ```
- **Known Event Identifiers (`eventParameter1` contains station terminal index):**
  - `97`: Station turned on.
  - `98`: Station turned off.
  - `15000`: Irrigation run completed.
  - `15001`: Automatic seasonal adjust changed.
  - `15002`: Rain delay enabled.
  - `15011`: Rain delay expired/disabled.
