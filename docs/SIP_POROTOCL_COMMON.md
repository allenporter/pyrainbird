# RainBird SIP Protocol — Common Specification

> Based on analysis of RainBird controller behavior and companion app v2.17.14

## Transport Layer

SIP commands are binary data encoded as **hex strings** and transported via **JSON-RPC** over HTTP or WebSocket.

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
| AlternateBitRateSupportRequest | `09` | — | Bit rate support check |
| ControllerFirmwareVersionRequest | `0B` | `8B` | Get firmware version |
| UniversalMessageRequest | `0C` | `8C` | **Universal/CDT message transport** |
| SetTimeRequest | `11` | `01` | Set current time |
| SetDateRequest | `13` | `01` | Set current date |
| RetrieveScheduleRequest | `20` | `A0` | Get schedule data page |
| SetSchedule | `21` | `01` | Set schedule data page |
| WaterBudgetSet | `31` | `01` | Set water budget |
| ZonesSeasonalAdjustFactorSet | `33` | `01` | Set per-zone seasonal adjust |
| RainDelaySetRequest | `37` | `01` | Set rain delay |
| ManuallyRunProgramRequest | `38` | `01` | Run program |
| CurrentStationErrorRequest | `3D` | — | Get station error (auto-increment) |
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
| SetTimeZoneRequest | `2B` | — | Set timezone |

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
| serialNumber | 2 | 16 | Controller serial number |

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

### `B2` — ZonesSeasonalAdjustFactorResponse
- **Length**: 18 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| programCode | 2 | 2 | Program/zone selector |
| stationsSA | 4 | 32 | Per-station seasonal adjust values |

### `B6` — RainDelaySettingResponse
- **Length**: 3 bytes

| Field | Position | Length | Description |
|-------|----------|--------|-------------|
| delaySetting | 2 | 4 | Rain delay in days |

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
| irrigationState | 2 | 2 | `1` = irrigating, `0` = idle |

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
| irrigationState | 20 | 2 | Irrigation state |
| seasonalAdjust | 22 | 4 | Seasonal adjust % |
| remainingRuntime | 26 | 4 | Remaining runtime (minutes) |
| activeStation | 30 | 2 | Currently active station number |

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
