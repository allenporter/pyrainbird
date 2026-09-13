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
| ESP_MEv2 | ESP-Me | `0107` | ✅ | 4 | 6 | 0 | 22 | Legacy SIP (ME) |
| ESP_TM2 | ESP-TM2 | `0005` | ✅ | 3 | 4 | 0 | 12 | Legacy SIP (TM2) |
| ESP_TM2v2 | ESP-TM2 | `000A` | ✅ | 3 | 4 | 0 | 12 | Legacy SIP (TM2 Upgraded) |
| ESP_TM2v3 | ESP-TM2 | `010A` | ✅ | 3 | 4 | 0 | 12 | Legacy SIP (TM2 Upgraded) |
| TM2R | ESP-TM2 | `0014` | ✅ | 3 | 4 | 0 | 12 | Legacy SIP (TM2 Upgraded) |
| TRU | TRU | `0015` | ✅ | 3 | 4 | 0 | 12 | Legacy SIP (TM2 Upgraded) |
| ESP_ME3 | ESP-ME3 | `0009` | ✅ | 4 | 6 | 1 | 22 | **Universal** |
| RC2 | RC2 | `0812` | ✅ | 3 | 4 | 0 | 8 | **Universal** (ISK) |
| ARC8 | ARC | `0813` | ✅ | 3 | 4 | 0 | 8 | **Universal** (ISK) |
| ESP_2WIRE | ESP-2WIRE | `0011` | ✅ | 4 | 6 | 1 | 50 | **Universal** |
| LXME2 | LXME2 | `000C` | ✅ | 40 | 10 | 1 | 48 | **Universal** (LX) |
| LX_IVM | LX-IVM | `000D` | ✅ | 10 | 8 | 1 | 60 | **Universal** (LX) |
| LX_IVM_PRO | LX-IVM Pro | `000E` | ✅ | 40 | 8 | 7 | 240 | **Universal** (LX) |
| TBOS_BT | TBOS-BT | `0099` | ✅ | 3 | 8 | 0 | 6 | BLE (Solem) |
| TBOS_BT_LT | TBOS-BT | `0100` | ✅ | 3 | 8 | 0 | 6 | BLE (Solem) |
| CBOS_BT | BAT-BT | `000B` | ✅ | 4 | 8 | 0 | 1 | BLE (Solem) |
| CBOS_BT_2 | BAT-BT | `000B` | ✅ | 4 | 8 | 0 | 2 | BLE (Solem) |
| CBOS_BT_4 | BAT-BT | `000B` | ✅ | 4 | 8 | 0 | 4 | BLE (Solem) |
| CBOS_BT_6 | BAT-BT | `000B` | ✅ | 4 | 8 | 0 | 6 | BLE (Solem) |
| ESP_BAT_PRO | BAT-Pro | `0016` | ✅ | 24 | 8 | 0 | 6 | BLE (Solem) |
| ESP_BAT_PRO_EU | BAT-Pro EU | `0017` | ✅ | 24 | 8 | 0 | 6 | BLE (Solem) |
| ESP_BAT_PRO_FLOW | BAT-Pro Flow | `0018` | ✅ | 24 | 8 | 0 | 6 | BLE (Solem) |
| ESP_BAT_PRO_FLOW_EU | BAT-Pro Flow EU | `0019` | ✅ | 24 | 8 | 0 | 6 | BLE (Solem) |
| MOCK_ESP_ME2 | ESP=Me2 | `0010` | ✅ | 4 | 6 | 0 | 22 | Legacy SIP (ME) |

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

### BAT-BT / BAT-PRO family (Battery Bluetooth / Solem protocol)
- **BAT-BT**: CBOS_BT, CBOS_BT_2, CBOS_BT_4, CBOS_BT_6
- **BAT-PRO**: ESP_BAT_PRO, ESP_BAT_PRO_EU, ESP_BAT_PRO_FLOW, ESP_BAT_PRO_FLOW_EU
- **TBOS-BT**: TBOS_BT, TBOS_BT_LT

---

## Feature Support Matrix

| Feature | RZXe | ST8 | ST8v2 | RZXe2 | ESP-ME | TM2 | TM2 Upgraded | ME3 | ISK | 2WIRE | LXME2 | LX-IVM |
|---------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Program-based | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Combined state (4C) | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Stacked watering (4B) | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ |
| Manual queue | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Soil type | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| SA by zone | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| SA by controller | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| SA per schedule | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Sensor bypass/zone | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Stats | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Weather settings | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Auto irrigation config | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Schedule timestamp | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Advance station (42) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Alarm.com | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Uses server data | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Homepage layout | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Ignore global WB | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

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
```
12          CurrentDateRequest
3D00        CurrentStationErrorRequest(page=0)
36          RainDelayGetRequest
3E          CurrentRainSensorStateRequest
4A01        ControllerEventTimestampRequest(page=1)
3000        GetWaterBudget(program=0)
3001        GetWaterBudget(program=1)
3002        GetWaterBudget(program=2)
4C          CombinedControllerStateRequest
3F00        CurrentStationsActiveRequest(page=0)
3B00        CurrentQueueRequest(page=0)
02          ControllerFirmwareVersionRequest
```

### ISK (RC2, ARC8)
Note: ISK does **not** poll `4C` (CombinedState) or `3F00` (CurrentStationsActive).
```
12          CurrentDateRequest
3D00        CurrentStationErrorRequest(page=0)
36          RainDelayGetRequest
3E          CurrentRainSensorStateRequest
4A01        ControllerEventTimestampRequest(page=1)
02          ControllerFirmwareVersionRequest
10          CurrentTimeRequest
3C          IrrigationStateRequest
3B00        CurrentQueueRequest(page=0)
3B01        CurrentQueueRequest(page=1)
3000        GetWaterBudget(program=0)
3001        GetWaterBudget(program=1)
3002        GetWaterBudget(program=2)
3800        AvailableStationsRequest(page=0)
0C20...     Universal CDT message (sensor bypass)
0C20...     Universal CDT message (logical dial position)
```

### ESP-ME3
Same as ISK + `48` (FlowSequenceStatus), `49` (FlowMonitorStatus), `3003` (WaterBudget program 3), without CurrentTime, IrrigationState, or dial position CDT.

### ESP-2WIRE
Same as ME3 + `3801` (AvailableStations page 1) + Universal CDT messages for alarms bitmap and module info.

### LX-IVM, LX-IVM Pro
```
02          ControllerFirmwareVersionRequest
3C          IrrigationStateRequest
3B00        CurrentQueueRequest(page=0)
3B01        CurrentQueueRequest(page=1)
48          LearnFlowSequenceStatusRequest
49          FlowMonitorStatusRequest
```

### LXME2
```
02          ControllerFirmwareVersionRequest
3C          IrrigationStateRequest
3B00        CurrentQueueRequest(page=0)
3B01        CurrentQueueRequest(page=1)
```
