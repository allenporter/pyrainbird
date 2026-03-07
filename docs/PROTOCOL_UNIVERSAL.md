# RainBird Protocol — Universal (CDT/UPT)

> ESP-ME3 (`0009`), RC2 (`0812`), ARC8 (`0813`), ESP-2WIRE (`0011`), LXME2 (`000C`), LX-IVM (`000D`), LX-IVM Pro (`000E`)

These controllers use the **Universal protocol** — a CDT (Controller Data Transfer) / UPT (Universal Protocol Transfer) layer that rides on top of the standard SIP transport via command `0C` / response `8C`.


---

## Architecture Overview

```
┌────────────────────────────────────┐
│         Application Logic          │
├────────────────────────────────────┤
│    Universal Message Builder       │
│    (builds CDT/UPT messages)       │
├────────────────────────────────────┤
│    SIP Command 0C / Response 8C    │
│    (Universal message transport)   │
├────────────────────────────────────┤
│    tunnelSip JSON-RPC              │
│    (HTTP/WebSocket transport)      │
└────────────────────────────────────┘
```

Universal messages are **pre-built hex strings** sent via the existing SIP `tunnelSip` RPC — the same transport as legacy SIP commands.

---

## Universal Message Structure

### Header Format

All Universal messages start with a standard header:

```
0C 20 00 01 00 SS SS 00 00 00 00 MM 00 00 00 00 00 05 00 00 00
```

| Offset | Bytes | Value | Description |
|--------|-------|-------|-------------|
| 0 | 1 | `0C` | SIP command code (Universal message) |
| 1-4 | 4 | `20000100` | Fixed protocol header |
| 5-6 | 2 | `SS SS` | Sub-protocol identifier |
| 7-10 | 4 | `00000000` | Fixed padding |
| 11 | 1 | `MM` | **Manager ID** (target subsystem) |
| 12-16 | 5 | `0000000005` | Fixed padding |
| 17-20 | 4 | `000000` | Fixed padding |

### Manager IDs

| Manager ID | Hex Constant | Purpose |
|-----------|-------|---------|
| `0C` | `universalHeaderCDT` | CDT data manager (schedules, config) |
| `09` | `irrigationManagerHeader` | Irrigation manager |
| `13` | `GUI_SCREEN_MANAGER_HEADER` | GUI screen manager |
| `03` | `SYSTEM_TIME_MANAGER_HEADER` | System time |
| `04` | `FIELD_DEVICES_MANAGER_HEADER` | Field devices (2-wire) |
| `0D` | `FIRMWARE_MANAGER_HEADER` / `universalHeaderRCP` | Firmware/RCP |
| `18` | `SESSION_MANAGER_HEADER` | Session manager |

### Payload Types

After the header, the payload is identified by a type code:

| Value | Name | Description |
|-------|------|-------------|
| 1 | CDT_DATA_SET_REQUEST | Set a single data ID |
| 2 | CDT_DATA_SET_RESPONSE | Response to set |
| 3 | CDT_DATA_GET_REQUEST | Get a single data ID |
| 4 | CDT_DATA_GET_RESPONSE | Response to get |
| 5 | CDT_DATA_BUNCH_SET_REQUEST | Set multiple data IDs |
| 6 | CDT_DATA_BUNCH_SET_RESPONSE | Response to batch set |
| 7 | CDT_DATA_BUNCH_GET_REQUEST | Get multiple data IDs |
| 8 | CDT_DATA_BUNCH_GET_RESPONSE | Response to batch get |
| 27 | CDT_DATA_BUNCH_GET_SAME_REQUEST | Get same ID for multiple indices |
| 28 | CDT_DATA_BUNCH_GET_SAME_RESPONSE | Response to same-ID batch get |

### CDT Data IDs

Data IDs identify what configuration or runtime data to read/write:

| ID (decimal) | ID (hex) | Name | Rank | Description |
|-------------|---------|------|------|-------------|
| 10 | `0A` | CDI_IRRIGATION_CYCLE_TIME | 1 | Cycle time per station |
| 11 | `0B` | CDI_IRRIGATION_SOAK_TIME | 1 | Soak time per station |
| 12 | `0C` | CDI_IRRIGATION_INTER_STATION_DELAY | 0 | Inter-station delay |
| 13 | `0D` | CDI_IRRIGATION_GLOBAL_SENSOR_BYPASS | 0 | Global sensor bypass |
| 16 | `10` | CDI_IRRIGATION_PROGRAM_CYCLE_CUSTOM_DAYS | 2 | Custom days per program |
| 17 | `11` | CDI_IRRIGATION_PROGRAM_CYCLE_WATER_CYCLE_CYCLE_COUNT | 1 | Cycle count per program |
| 18 | `12` | CDI_IRRIGATION_PROGRAM_CYCLE_WATER_CYCLE_CYCLE_DAYS | 1 | Cycle days per program |
| 19 | `13` | CDI_IRRIGATION_PROGRAM_CYCLE_WATER_CYCLE_TYPE | 1 | Cycle type per program |
| 20 | `14` | CDI_IRRIGATION_RAIN_DELAY | 0 | Rain delay |
| 21 | `15` | CDI_IRRIGATION_RUN_TIMES | 2 | Run times (per-program per-station) |
| 24 | `18` | CDI_IRRIGATION_SEASONAL_ADJUST_BY_PROGRAM | 1 | Seasonal adjust per program |
| 29 | `1D` | CDI_IRRIGATION_START_TIMES | 3 | Start times (per-program) |
| 38 | `26` | CDI_FLOW_MONITOR_HIGH_FLOW_ACTION | 0 | High flow action |
| 39 | `27` | CDI_FLOW_MONITOR_HIGH_FLOW_SETTLE_TIME | 0 | High flow settle time |
| 40 | `28` | CDI_FLOW_MONITOR_HIGH_FLOW_THRESHOLD | 0 | High flow threshold |
| 41 | `29` | CDI_FLOW_MONITOR_LOW_FLOW_ACTION | 0 | Low flow action |
| 42 | `2A` | CDI_FLOW_MONITOR_LOW_FLOW_SETTLE_TIME | 0 | Low flow settle time |
| 43 | `2B` | CDI_FLOW_MONITOR_LOW_FLOW_THRESHOLD | 0 | Low flow threshold |
| 61 | `3D` | CDI_FLOW_MANAGER_STATION_FLOW | 1 | Station flow rates |
| 62 | `3E` | CDI_FLOW_MANAGER_STATIONS_LEARNED | 1 | Learned flow per station |
| 77 | `4D` | CDI_MODULE_CONFIGURATION_FLOW_SENSOR_TYPE | 1 | Flow sensor type |
| 79 | `4F` | CDI_MODULE_CONFIGURATION_FLOW_K_FACTOR | 1 | Flow sensor K-factor |
| 80 | `50` | CDI_MODULE_CONFIGURATION_FLOW_OFFSET | 1 | Flow sensor offset |

The **rank** field indicates the index dimension — rank 0 = scalar, rank 1 = indexed by station or program, rank 2 = indexed by program×station, rank 3 = multi-dimensional.

---

## Per-Controller Schedule Commands

Each controller family has a pre-defined set of CDT batch-get commands for fetching schedule data. These are fired sequentially when the app opens the schedule screen.

### ESP-ME3 (8 messages)

| # | Command | CDT Data IDs Requested |
|---|---------|----------------------|
| 1 | Start times | `1D` (START_TIMES) — rank 3 — all programs |
| 2 | Program 1 runtimes | `15` (RUN_TIMES) — program 0, all stations |
| 3 | Program 2 runtimes | `15` (RUN_TIMES) — program 1, all stations |
| 4 | Program 3 runtimes | `15` (RUN_TIMES) — program 2, all stations |
| 5 | Program 4 runtimes | `15` (RUN_TIMES) — program 3, all stations |
| 6 | Cycle/soak | `0A` (CYCLE_TIME) + `0B` (SOAK_TIME) — per station |
| 7 | Frequency/cycle days | `12` (CYCLE_DAYS) + `11` (CYCLE_COUNT) + `10` (CUSTOM_DAYS) — per program |
| 8 | Sensor & adjust | `14` (RAIN_DELAY) + `0D` (SENSOR_BYPASS) + `18` (SEASONAL_ADJUST) + `13` (CYCLE_TYPE) — per program |

### ISK — RC2, ARC8 (7 messages)

| # | Command | CDT Data IDs Requested |
|---|---------|----------------------|
| 1 | Start times | `1D` (START_TIMES) — rank 3, 3 programs × 4 start times |
| 2 | Program 1 runtimes | `15` (RUN_TIMES) — program 0, 7 stations |
| 3 | Program 2 runtimes | `15` (RUN_TIMES) — program 1, 7 stations |
| 4 | Program 3 runtimes | `15` (RUN_TIMES) — program 2, 7 stations |
| 5 | Cycle/soak | `0A` + `0B` — 7 stations |
| 6 | Frequency/cycle days | Full set including `14`, `0D`, `18`, `13`, `12`, `11`, `10` — 3 programs |
| 7 | Sensor & adjust | `14` + `0D` + `18` + `13` — 3 programs |

### ESP-2WIRE (13 messages)

Extends ME3 with 8 runtime pages (for up to 50 stations across 4 programs):
- Programs 1-4, each split into 2 station-range requests (stations 0-24, 25-49)
- Separate cycle/soak for each station range
- Same frequency and sensor/adjust commands as ME3

---

## Response Parsing

### Universal Response Structure

Universal responses come back via SIP response `8C`. The response contains:

| Offset (byte) | Field | Description |
|--------------|-------|-------------|
| 0-20 | Header | 21-byte Universal header |
| 21 | Response data size | Number of data bytes following |
| 23 | Payload type | CDT response type (e.g., 8 = BUNCH_GET_RESPONSE) |
| 25 | Block count / ACK-NACK | Number of data blocks or ACK/NACK summary |

### Data Extraction

Response data uses **little-endian** byte order (unlike legacy SIP which is big-endian). Multi-byte values must be byte-swapped when converting from raw response data.

**Runtime values** from Universal responses are in **seconds** and must be divided by 60 to convert to minutes (the display/storage unit).

### Queue Response — Universal Format

The Universal queue response reuses SIP command `3B`/response `BB` but with different byte order:

#### Page 0 — Running State
```
BB 00 ?? TT SSSS
```
- `TT` = irrigation type at offset [6:8]
- `SSSS` = stations running count at offset [8:12] — **little-endian** 2-byte value

#### Page 1+ — Pending Entries (8 entries × 12 hex chars)
```
BB PP [SSSS RRRRRRRR] ×8
```
Per entry:
- `SSSS` (4 hex chars) = station number (big-endian, offset relative)
- `RRRRRRRR` (8 hex chars) = remaining time — **little-endian** 4-byte value
- Entry with station = 0 terminates the list
- Only included if remaining time > 0

---

## 2-Wire Specific Features

ESP-2WIRE controllers have additional capabilities:

### Alarm Bitmaps
Command: `1330` (GET_ALARMS_BITMAP) via the alarms manager
- Returns a bitmap of active alarms

### Module Info
Command: `220B` (GET_MODULE_INFO) / Response: `230B`
- Query firmware module information for installed modules
- Module slot addresses: slot 0 = `F90000000000`, slot 1 = `010000000000`

### Field Device Management
- `4109` AUTO_ASSIGN_ADDRESSES
- `4809` / `4909` CLEAR_ALL_ADDRESSES
- `4A09` / `4B09` CLEAR_SINGLE_ADDRESS
- `4C09` / `4D09` GET_DISCOVERY_PROGRESS
- `4E09` / `4F09` GET_DISCOVERY_RESULTS
- `3D09` / `3E09` DISCOVERY_START_STOP
- `2F09` / `3009` GET_TWO_WIRE_LINE_SURVEY
- `5009` / `5109` REFRESH_ADDRESS_ASSIGNMENTS

### AC Current Test
- `1F50` AC_CURRENT_TEST / `2050` AC_CURRENT_TEST_RESPONSE
- `2350` TWO_WIRE_DIAGNOSTICS / `2450` TWO_WIRE_DIAGNOSTICS_RESPONSE

---

## Front Panel Session Management

Universal controllers support locking/unlocking the physical front panel:

| Command | Code | Description |
|---------|------|-------------|
| FRONT_PANEL_SESSION_START | `0114` | Request front panel lock |
| FRONT_PANEL_SESSION_START_REPLY | `0214` | Lock confirmed |
| FRONT_PANEL_SESSION_END | `0314` | Release front panel |
| FRONT_PANEL_SESSION_END_REPLY | `0414` | Release confirmed |
| FRONT_PANEL_SESSION_BEACON | `0714` | Keep-alive beacon |
| FRONT_PANEL_SESSION_BEACON_REPLY | `0814` | Beacon response |

---

## Firmware Update Protocol (RCP)

Universal controllers support over-the-air firmware updates using the RCP (Remote Code Programming) sub-protocol:

| Payload Type | Value | Description |
|-------------|-------|-------------|
| UPT_RCP_ACK | 15 | Firmware update acknowledged |
| UPT_RCP_NACK | 16 | Firmware update rejected |
| UPT_RCP_START_REQUEST | 17 | Initiate firmware update |
| UPT_RCP_READY_REQUEST | 18 | Ready to receive |
| UPT_RCP_BLOB_TRANSMIT | 19 | Send firmware blob |
| UPT_RCP_CRC_CHECK_START_REQUEST | 20 | Start CRC verification |
| UPT_RCP_CRC_CHECK_QUERY | 21 | Query CRC status |
| UPT_RCP_CRC_CHECK_QUERY_RESPONSE | 22 | CRC check result |
| UPT_RCP_COMMIT | 23 | Commit firmware update |

**Bundled firmware versions** (as of app v2.17.14):
- ESP-ME3: FW 2.41, Bootloader 0.24
- ISK (RC2/ARC8): FW 2.107
- ESP-2WIRE: FW 1.24, TX FW 1.5

---

## Logical Dial Position

ISK controllers (RC2, ARC8) use a logical dial concept for UI state:
- `0A30` GET_LOGICAL_DIAL / `0B30` GET_LOGICAL_DIAL_RESPONSE
- `2D30` SET_LOGICAL_DIAL / `2E30` SET_LOGICAL_DIAL_RESPONSE

Polling command: `0C200001000805000000001300000000000500000002000A30`

---

## Key Differences from Legacy SIP

| Aspect | Legacy SIP | Universal |
|--------|-----------|-----------|
| Byte order | Big-endian | **Little-endian** |
| Runtime units | Minutes | **Seconds** (÷60 for display) |
| Schedule fetch | Page-by-page requests (`20 00 PP`) | Pre-built batch CDT messages |
| Message format | Simple hex command + args | Header (21 bytes) + payload type + data blocks |
| Data addressing | Page numbers | CDT Data IDs with rank/index |
| Firmware update | Not supported | Full RCP protocol |
| Front panel lock | Not supported | Session management |
