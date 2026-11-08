# RainBird SIP Protocol — Common Specification

> Based on analysis of RainBird controller behavior, companion app v2.17.14, LNK2 firmware v4.136.0 (`sip_manchester.cpp`), and hardware captures ([Discussion #611](https://github.com/allenporter/pyrainbird/discussions/611))

## Transport Layer

SIP commands are binary data encoded as **hex strings** when transported over the network via **JSON-RPC** (HTTP or WebSocket), and transmitted as **framed binary bytes** over the 5-pin accessory port between the LNK/LNK2 WiFi module and the irrigation controller faceplate.

### JSON-RPC Wrapper

All SIP commands are sent using the `tunnelSip` RPC method:

```json
{
  "jsonrpc": "2.0",
  "method": "tunnelSip",
  "params": {
    "length": <number_of_sip_bytes>,
    "data": "<hex_string>"
  },
  "id": <seq>
}
```

Response:
```json
{
  "jsonrpc": "2.0",
  "result": {
    "length": <number_of_sip_bytes>,
    "data": "<hex_string>"
  },
  "id": <seq>
}
```

### Hex Encoding

- Each SIP byte is represented as **2 hex characters** (nibbles)
- The first byte of a command/response is the **command code** (e.g., `02` = ModelAndVersionRequest)
- Positions in the schema below are in **nibble offsets** (hex char positions)
- Lengths in the schema are in **nibble counts** (hex char counts)

### Physical Layer & Serial Wire Framing (LNK / LNK2 Accessory Port)

Between the LNK/LNK2 WiFi module and the controller faceplate (verified via oscilloscope capture on ESP-TM2 + LNK2 and LNK2 firmware `./components/ctrl_comm/sip_manchester.cpp`):

#### 5-Pin Accessory Connector Pinout
| Pin | Signal | Direction / Notes |
|-----|--------|-------------------|
| J1 | 24 VAC | Power |
| J2 | Controller TX | Controller to LNK2 ESP32 GPIO 25 (via optocoupler) |
| J3 | Signal Return | Common reference for optocoupler LEDs |
| J4 | Controller RX | LNK2 ESP32 GPIO 26 to Controller (via optocoupler) |
| J5 | 24 VAC | Power |

#### Baseline Manchester Encoding (2400 bit/s)
- **Bit rate**: 2400 bit/s (half-bit period $\approx 208\ \mu\text{s}$, full-bit period $\approx 416\ \mu\text{s}$; LNK2 RMT receiver discriminates half vs. full bit widths using a 391-tick threshold `0x187`).
- **Line coding**: Differential/Manchester encoding, MSB first, no start/stop/parity bits, line idles low (`0`):
  - `1` = High-then-Low transition (`10`)
  - `0` = Low-then-High transition (`01`)

#### Wire Frame Structure
```text
Module -> Controller (TX):  F5 F5    1C <len> <payload...> <chk> 1D
Controller -> Module (RX):  F5 F5 F5 1C <len> <payload...> <chk> 1D
```
- **Sync Preamble (`F5`)**: 2 bytes (`F5 F5`) from LNK module to controller; 3 bytes (`F5 F5 F5`) from controller to LNK module. The receiver synchronizes its byte boundary on `0xF5` before waiting for `0x1C`.
- **Start of Frame (`1C`)**: Unescaped byte `0x1C` marks the start of the frame.
- **Length (`<len>`)**: 1 byte — number of unescaped SIP `<payload>` bytes (matches the JSON-RPC `length` field).
- **Payload (`<payload...>`)**: Raw SIP command or response bytes (matches the JSON-RPC `data` hex string).
- **Checksum (`<chk>`)**: 1 byte — 8-bit unsigned sum of the unescaped `<len>` byte and all unescaped `<payload>` bytes:
  $$\text{chk} = \left(\text{len} + \sum_{i} \text{payload}[i]\right) \bmod 256$$
- **End of Frame (`1D`)**: Unescaped byte `0x1D` marks the end of the frame.

#### Byte Stuffing (Escape Sequences)
Because `0x1C` (STX) and `0x1D` (ETX) are framing delimiters, any occurrence of `0x1B`, `0x1C`, or `0x1D` inside `<len>`, `<payload>`, or `<chk>` is escaped on the wire using `0x1B` (ESC):

| Unescaped Byte | Wire Representation | Meaning |
|----------------|---------------------|---------|
| `0x1C` | `1B 01` | Escaped `0x1C` (STX) |
| `0x1B` | `1B 02` | Escaped `0x1B` (ESC) |
| `0x1D` | `1B 03` | Escaped `0x1D` (ETX) |

> **Note**: Length and checksum calculations are performed on the **unescaped** bytes before TX byte-stuffing / after RX unescaping.

#### High-Speed UART Mode & Inter-Controller Handshake
LNK2 firmware also includes a secondary UART transport driver on UART2 (GPIO 26 TX, GPIO 25 RX):
- Negotiated via `09` (`AlternateBitRateSupportRequest` / `0A`) or `0D` / `0E` baud-rate negotiation commands.
- Uses `1C` (STX), `1D` (ETX), and the same `1B 01` / `1B 02` / `1B 03` byte-stuffing rules, but replaces the 1-byte length with a 2-byte little-endian length and replaces the additive checksum with an 8-bit table-driven CRC.
- During link initialization, LNK2 tests command support (`04 04` → `84 04 01`) and can perform a challenge-response handshake using commands `06` (response `86`) and `07` (response `87`).

#### LNK2 Background Polling Sequence
When connected to a controller (such as ESP-TM2), the LNK2 module periodically polls controller state in the background (~every 10 seconds when idle, ~every 1 second while irrigating) to synchronize state with the Rain Bird cloud (`0xF9` binary property reports):
`12` → `3F 00` → `3F 01` → `3D 00`..`02` → `36` → `3E` → `4A 01` → `30 00`..`02` → `4C` → `3B 00` → `0B` → `10`.

---

## Command Reference

These commands are defined in the controller's embedded command schema (`sipcommands.json`).

### Commands (ControllerCommands)

| Command | Code | Response | Length (bytes) | Parameters | Description |
|---------|------|----------|----------------|------------|-------------|
| ModelAndVersionRequest | `02` | `82` | 1 | — | Get controller model ID and protocol version |
| AvailableStationsRequest | `03` | `83` | 2 | `parameter`: page number | Get available stations bitmask for a page |
| CommandSupportRequest | `04` | `84` | 2 | `commandToTest`: cmd code | Test if a command is supported |
| SerialNumberRequest | `05` | `85` | 1 | — | Get serial number |
| CurrentTimeRequest | `10` | `90` | 1 | — | Get current time |
| CurrentDateRequest | `12` | `92` | 1 | — | Get current date |
| WaterBudgetRequest | `30` | `B0` | 2 | `parameter`: program code | Get water budget (seasonal adjust) |
| ZonesSeasonalAdjustFactorRequest | `32` | `B2` | 2 | `parameter`: zone selector | Get per-zone seasonal adjust |
| CurrentRainSensorStateRequest | `3E` | `BE` | 1 | — | Get rain sensor state |
| CurrentStationsActiveRequest | `3F` | `BF` | 2 | `parameter`: page number | Get currently active stations |
| ManuallyRunProgramRequest | `38` | `01` | 2 | `parameter`: program number | Run a program |
| ManuallyRunStationRequest | `39` | `01` | 4 | `parameterOne`: station, `parameterTwo`: duration | Run a station manually |
| TestStationsRequest | `3A` | `01` | 2 | `parameter`: duration | Test all stations |
| StopIrrigationRequest | `40` | `01` | 1 | — | Stop all irrigation |
| RainDelayGetRequest | `36` | `B6` | 1 | — | Get rain delay setting |
| RainDelaySetRequest | `37` | `01` | 3 | `parameter`: delay days | Set rain delay |
| AdvanceStationRequest | `42` | `01` | 2 | `parameter`: station | Advance to next station |
| CurrentIrrigationStateRequest | `48` | `C8` | 1 | — | Get irrigation state |
| CurrentControllerStateSet | `49` | `01` | 2 | `parameter`: state | Set controller state |
| ControllerEventTimestampRequest | `4A` | `CA` | 2 | `parameter`: event ID | Get event timestamp |
| StackManuallyRunStationRequest | `4B` | `01` | 4 | `parameter`, `parameterTwo`, `parameterThree` | Stack a manual station run |
| CombinedControllerStateRequest | `4C` | `CC` | 1 | — | Get combined state (time, date, delay, sensor, irrigation) |

### Additional Commands (from SIPCommandKeys enum, not in sipcommands.json)

| Command | Code | Response | Description |
|---------|------|----------|-------------|
| AlternateBitRateSupportRequest | `09` | `0A` | Bit rate support check / negotiation |
| ControllerFirmwareVersionRequest | `0B` | `8B` | Get firmware version |
| UniversalMessageRequest | `0C` | `8C` | **Universal/CDT message transport** |
| SetTimeRequest | `11` | `01` | Set current time |
| SetDateRequest | `13` | `01` | Set current date |
| RetrieveScheduleRequest | `20` | `A0` | Get schedule data page |
| SetSchedule | `21` | `01` | Set schedule data page |
| StackManuallyRunStationSecond / SetTimeZoneRequest | `2B` | `01` | Stack manual station run in seconds (`2B <stn:2B> <sec:2B>` in RB 2.0 BLE/SIP; listed as `SetTimeZoneRequest` in legacy `SIPCommandKeys`) |
| TestAllStationsSecond | `2C` | `01` | Test all stations with duration in seconds (`2C <sec:2B>`, RB 2.0 BLE/SIP) |
| PauseIrrigation | `2D` | `01` | Pause active irrigation (RB 2.0 BLE/SIP) |
| ResumeIrrigation | `2E` | `01` | Resume paused irrigation (RB 2.0 BLE/SIP) |
| WaterBudgetSet | `31` | `01` | Set water budget |
| ZonesSeasonalAdjustFactorSet / SetMonthlyWaterBudget | `33` | `01` | Set per-zone seasonal adjust (LCR / legacy SIP) or monthly water budget (`33 <month> <pct:2B>` on BLE/CBOS) |
| RainDelaySetRequest | `37` | `01` | Set rain delay |
| ManuallyRunProgramRequest | `38` | `01` | Run program |
| CurrentQueueRequest | `3B` | `BB` | Get current active / queued station status |
| CurrentStationErrorRequest | `3D` | `BD` | Get station electrical/short/open error bitmask (paged `3D PP` on ESP-TM2/ME3) |
| CurrentControllerStateSet | `49` | `01` | Set controller state |
| StackManuallyRunStationRequest | `4B` | `01` | Stack manual station |
| CombinedControllerStateRequest | `4C` | `CC` | Combined state request |
| IrrigationStatisticsRequest | `4D` | `CD` | Get irrigation statistics |
| StartLearnFlowSequenceRequest | `60` | `E0` | Start flow learning |
| CancelLearnFlowSequenceRequest | `61` | `E0` | Cancel flow learning |
| LearnFlowSequenceStatusRequest | `62` | `E2` | Get flow learning status |
| FlowMonitorStatusRequest | `63` | `E3` | Get flow monitor status |
| FlowMonitorStatusSetRequest | `64` | `64` | Set flow monitor status |
| FlowMonitorRateRequest | `65` | `E5` | Get flow monitor rate |
| LogEntriesRequest | `70` | — | Get log entries |

---

## Response Schemas (ControllerResponses)

### `00` — NotAcknowledgeResponse (NAK)
- **Length**: 3 bytes (6 hex chars)

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| commandEcho | 2 | 2 | Echo of the command code that was rejected |
| NAKCode | 4 | 2 | Error bitmask |

**NAK Error Codes** (bit positions in NAKCode):
| Bit | Code | Meaning |
|-----|------|---------|
| 0 | `01` | Command Not Supported |
| 1 | `02` | Bad Length |
| 2 | `04` | Incompatible Data |
| 3 | `08` | Checksum Error |

### `01` — AcknowledgeResponse (ACK)
- **Length**: 2 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| commandEcho | 2 | 2 | Echo of the command code that was acknowledged |

### `82` — ModelAndVersionResponse
- **Length**: 5 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| modelID | 2 | 4 | Controller model ID (e.g., `0007` = ESP-Me) |
| protocolRevisionMajor | 6 | 2 | Protocol major version |
| protocolRevisionMinor | 8 | 2 | Protocol minor version |

### `83` — AvailableStationsResponse
- **Length**: 6 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| pageNumber | 2 | 2 | Page number |
| setStations | 4 | 8 | Bitmask of available stations on this page |

### `84` — CommandSupportResponse
- **Length**: 3 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| commandEcho | 2 | 2 | Command code tested |
| support | 4 | 2 | `01` = supported, `00` = not supported |

### `85` — SerialNumberResponse
- **Length**: 9 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| serialNumber | 2 | 16 | Controller serial number (note: ESP-RZXe hardware returns `0000000000000000`) |

### `8B` — ControllerFirmwareVersionResponse
- **Length**: 5 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| major | 2 | 2 | Firmware major version |
| minor | 4 | 2 | Firmware minor version |
| patch | 6 | 4 | Firmware patch / build version |

### `90` — CurrentTimeResponse
- **Length**: 4 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| hour | 2 | 2 | Hour (0-23) |
| minute | 4 | 2 | Minute (0-59) |
| second | 6 | 2 | Second (0-59) |

### `92` — CurrentDateResponse
- **Length**: 4 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| day | 2 | 2 | Day of month |
| month | 4 | 1 | Month (1 hex nibble) |
| year | 5 | 3 | Year (3 hex nibbles) |

### `B0` — WaterBudgetResponse
- **Length**: 4 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| programCode | 2 | 2 | Program code |
| seasonalAdjust | 4 | 4 | Seasonal adjust value (percentage) |

### `B2` — ZonesSeasonalAdjustFactorResponse / MonthlyWaterBudgetResponse
- **Length**: 18 bytes on LCR / legacy SIP (`B2 <selector> <16B station SA>`); 4 bytes on BLE/CBOS (`B2 <month> <pct:2B>`)

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| programCode / month | 2 | 2 | Program/zone selector (`FF` on LCR) or month index (`00`..`0B` on BLE/CBOS) |
| stationsSA / seasonalAdjust | 4 | 32 (or 4) | Per-station seasonal adjust values (16 bytes = 32 hex chars) or 2-byte monthly percentage (4 hex chars) |

### `B6` — RainDelaySettingResponse
- **Length**: 3 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| delaySetting | 2 | 4 | Rain delay in days |

### `BD` — CurrentStationErrorResponse
- **Length**: 6 bytes on paged controllers (`3D PP` → `BD PP EEEEEEEE`, e.g. ESP-TM2 / ESP-ME3)

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| pageNumber | 2 | 2 | Echo of requested page (`00`..`02`) |
| stationErrors | 4 | 8 | Bitmask of station electrical/short errors (`00000000` = no errors) |

### `BE` — CurrentRainSensorStateResponse
- **Length**: 2 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| sensorState | 2 | 2 | `0` = sensor active (rain detected), `1` = no rain |

### `BF` — CurrentStationsActiveResponse
- **Length**: 6 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| pageNumber | 2 | 2 | Page number |
| activeStations | 4 | 8 | Bitmask of currently running stations |

### `C8` — CurrentIrrigationStateResponse
- **Length**: 2 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| irrigationState | 2 | 2 | `1` = auto-run enabled / irrigating, `0` = off / idle |

> **Hardware Note (ESP-RZXe)**: On ESP-RZXe (`0x0003`), `0x48` (`C8`) reports `01` when the controller's schedule mode is enabled (armed), even when no zone is currently watering. `0x3F` (`BF`, `CurrentStationsActiveRequest`) is the authoritative source for whether a station is actively running.

### `CA` — ControllerEventTimestampResponse
- **Length**: 6 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| eventId | 2 | 2 | Event type ID |
| timestamp | 4 | 8 | Timestamp value |

### `CC` — CombinedControllerStateResponse
- **Length**: 16 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| hour | 2 | 2 | Current hour |
| minute | 4 | 2 | Current minute |
| second | 6 | 2 | Current second |
| day | 8 | 2 | Current day |
| month | 10 | 1 | Current month |
| year | 11 | 3 | Current year |
| delaySetting | 14 | 4 | Rain delay days |
| sensorState | 18 | 2 | Rain sensor state |
| irrigationState | 20 | 2 | Irrigation state (`1` = auto/enabled, `0` = off) |
| seasonalAdjust | 22 | 4 | Seasonal adjust % |
| remainingRuntime | 26 | 4 | Remaining runtime in **seconds** (big-endian, e.g. `0167` = 359 s) |
| activeStation | 30 | 2 | Currently active station number (`00` = none) |

---

## Response Parsing Algorithm

All responses are parsed using a generic field-extraction algorithm:

```
1. Read the first 2 hex chars → command code
2. Look up the command code in ControllerResponses JSON
3. Verify: len(hex_string) / 2 == schema.length
4. For each field in the schema (skip "length" and "type"):
     field_value = hex_string[field.position : field.position + field.length]
5. Return map of {field_name: hex_value_string}
```

> **Important**: Position and length values are in **hex character counts** (nibbles), not bytes.

---

## Auto-Follow Behavior

After certain SET commands, the app automatically sends the corresponding GET:
- `SetTimeRequest (11)` → auto-sends `CurrentTimeRequest (10)`
- `SetDateRequest (13)` → auto-sends `CurrentDateRequest (12)`
- `RainDelaySetRequest (37)` → auto-sends `RainDelayGetRequest (36)`
