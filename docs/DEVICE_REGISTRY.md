# RainBird Device Registry

This page documents details about Rainbird Device types and various levels of supported features.

## Controller Types

| Enum Name | Series | Model ID | Program-Based | Max Programs | Max Start Times | Max Station Pages | Max Stations | Protocol |
|-----------|--------|----------|:---:|:---:|:---:|:---:|:---:|----------|
| ESP_RZXe | ESP-RZXe | `0003` | ❌ | 0 | 6 | 0 | 8 | Legacy SIP (LCR) |
| ESP_RZXe2 | ESP-RZXe2 | `0103` | ❌ | 8 | 6 | 0 | 8 | Legacy SIP (LCR) |
| ST8X_WF | ST8x-WiFi | `0006` | ❌ | 0 | 6 | 0 | 8 | Legacy SIP (LCR) |
| ST8X_WF2 | ST8x-WiFi2 | `0008` | ❌ | 8 | 6 | 0 | 8 | Legacy SIP (LCR) |
| ESP_ME | ESP-Me | `0007` | ✅ | 4 | 6 | 0 | 22 | Legacy SIP (ME) |
| ESP_TM2 | ESP-TM2 | `0005` | ✅ | 3 | 4 | 0 | 12 | Legacy SIP (TM2) |
| ESP_TM2v2 | ESP-TM2 | `000A` | ✅ | 3 | 4 | 0 | 12 | Legacy SIP (TM2 Upgraded) |
| ESP_TM2v3 | ESP-TM2 | `010A` | ✅ | 3 | 4 | 0 | 12 | Legacy SIP (TM2 Upgraded) |
| TM2R | ESP-TM2 | `0014` | ✅ | 3 | 4 | 0 | 12 | Legacy SIP (TM2 Upgraded) |
| TRU | TRU | `0015` | ✅ | 3 | 4 | 0 | 12 | Legacy SIP (TM2 Upgraded) |
| ESP_ME3 | ESP-ME3 | `0009` | ✅ | 4 | 6 | 0 | 22 | **Universal** |
| RC2 | RC2 | `0812` | ✅ | 3 | 4 | 0 | 12 | **Universal** (ISK) |
| ARC8 | ARC | `0813` | ✅ | 3 | 4 | 0 | 12 | **Universal** (ISK) |
| ESP_2WIRE | ESP-2WIRE | `0011` | ✅ | 4 | 6 | 1 | 50 | **Universal** |
| LXME2 | LXME2 | `000C` | ✅ | 40 | 10 | 1 | 22* | **Universal** (LX) |
| LX_IVM | LX-IVM | `000D` | ✅ | 10 | 8 | 1 | 22* | **Universal** (LX) |
| LX_IVM_PRO | LX-IVM Pro | `000E` | ✅ | 40 | 8 | 7 | 22* | **Universal** (LX) |
| TBOS_BT | TBOS-BT | `0099` | ✅ | 3 | 8 | 0 | — | BLE (Solem) |
| TBOS_BT_LT | TBOS-BT | `0100` | ✅ | 3 | 8 | 0 | — | BLE (Solem) |
| CBOS_BT | ESP-BAT-BT | `0011` | ✅ | 4 | 8 | 0 | — | BLE (Solem) |
| CBOS_BT_2 | ESP-BAT-BT | `0011` | ✅ | 4 | 8 | 0 | — | BLE (Solem) |
| CBOS_BT_4 | ESP-BAT-BT | `0011` | ✅ | 4 | 8 | 0 | — | BLE (Solem) |
| CBOS_BT_6 | ESP-BAT-BT | `0011` | ✅ | 4 | 8 | 0 | — | BLE (Solem) |
| MOCK_ESP_ME2 | ESP=Me2 | `0010` | ✅ | 4 | 6 | 0 | 22 | Legacy SIP (ME) |

*LX controllers default to 22 max stations.

---

## Device Groupings

We can group controllers into families that can help us better understand
the device capabilities.

### Non-program-based, per-zone schedule (LCR Series)
- ST8X_WF, ST8X_WF2, ESP_RZXe, ESP_RZXe2

### TM2 family
- **TM2**: ESP_TM2, ESP_TM2v2, ESP_TM2v3, TM2R, TRU
- **Upgraded TM2**: ESP_TM2v2, ESP_TM2v3, TM2R, TRU (excludes original ESP_TM2)

### ISK family (Universal protocol)
- RC2, ARC8

### LX family (Universal protocol)
- LXME2, LX_IVM, LX_IVM_PRO

### Universal/CDT protocol
- ESP_ME3, RC2, ARC8, ESP_2WIRE, LXME2, LX_IVM, LX_IVM_PRO

---

## Feature Support Matrix

| Feature | RZXe | ST8 | ST8v2 | RZXe2 | ESP-ME | TM2 | TM2 Upgraded | ME3 | ISK | 2WIRE | LX |
|---------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Program-based | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Combined state (4C) | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Stacked watering (4B) | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Manual queue | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Soil type | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| SA by zone | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| SA by controller | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| SA per schedule | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Sensor bypass/zone | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Stats | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Weather settings | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Auto irrigation config | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Schedule timestamp | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Advance station (42) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Alarm.com | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Uses server data | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Homepage layout | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Ignore global WB | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |

---

## Auto-Queue Polling Commands

Each controller type defines a set of SIP commands that the app polls in a loop. Here are the distinct groups:

### Default (ESP-RZXe, ESP-ME, ESP-TM2)
```
12          CurrentDateRequest
3D00        CurrentStationErrorRequest(page=0)
36          RainDelayGetRequest
3E          CurrentRainSensorStateRequest
```

### ST8x-WiFi2, ESP-RZXe2
Above + `4A01` (EventTimestamp), `4C` (CombinedState), `32FF` (ZonalSA)

### Upgraded TM2 (TM2v2, TM2v3, TM2R, TRU)
Above + WaterBudget ×3 (`3000`, `3001`, `3002`), CombinedState, CurrentStationsActive, CurrentQueue, FirmwareVersion

### ISK (RC2, ARC8)
Above + queue ×2, WaterBudget ×3, AvailableStations, FirmwareVersion, Time, IrrigationState + **2 Universal CDT messages** (sensor bypass + logical dial position)

### ESP-ME3
Above + FlowSequenceStatus, FlowMonitorStatus, WaterBudget ×4, AvailableStations + **1 Universal CDT message** (sensor bypass)

### ESP-2WIRE
Same as ME3 + additional AvailableStations page + **Universal CDT messages** for alarms bitmap and module info

### LX-IVM, LX-IVM Pro
FirmwareVersion, IrrigationState, CurrentQueue ×2, FlowSequenceStatus, FlowMonitorStatus

### LXME2
Same as LX-IVM + CurrentQueue ×2
