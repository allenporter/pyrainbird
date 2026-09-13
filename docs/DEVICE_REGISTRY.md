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

---

## Manufacturer Documentation & Technical Specifications

Official Rain Bird technical specification sheets and user manuals verifying controller hardware limits, program capacities, and supported features:

| Controller Family | Model Names / Series | Tech Spec PDF | User Manual PDF |
|---|---|---|---|
| **ESP-LXME2** | LXME2 (`000C`) | [ESP-LXME2 Tech Spec](https://www.rainbird.com/sites/default/files/media/documents/2021-09/d41999_lxme2_tech_spec_dom_en.pdf)<br>[Pro Smart Tech Spec](https://www.rainbird.com/sites/default/files/media/documents/2021-08/d41999_lxme2_pro_smart_tech_spec_dom_en.pdf) | [LXME2 User Manual](https://www.rainbird.com/sites/default/files/media/documents/2022-02/lxme2manual01_21_2022_2.pdf) |
| **ESP-LXIVM** | LX-IVM (`000D`), LX-IVM Pro (`000E`) | [ESP-LXIVM Tech Spec](https://www.rainbird.com/sites/default/files/media/documents/2020-09/d41695_esp-lxivm-tech-spec-dom_en.pdf)<br>[LXIVM Spec Sheet](https://www.rainbird.com/sites/default/files/media/documents/2020-05/ts_ESP-LXIVM_en.pdf) | [LXIVM User Manual](https://www.rainbird.com/sites/default/files/media/documents/2024-03/d41696_esp-lxivm-install-operation-guide_en.pdf) |
| **ESP-ME3** | ESP-ME3 (`0009`) | [ESP-ME3 Tech Spec](https://www.rainbird.com/sites/default/files/media/documents/2020-03/d41298_10de19_esp-me3-tech-spec-dom_en.pdf) | [ESP-ME3 User Manual](https://www.rainbird.com/sites/default/files/media/documents/2020-03/d41274_15ja20_esp-me3-user-manual-advanced-dom_en-en.pdf) |
| **ESP-TM2** | TM2 (`0005`, `000A`, `010A`, `0014`, `0015`) | [ESP-TM2 Tech Spec](https://www.rainbird.com/sites/default/files/media/documents/2019-02/ts_ESP-TM2_en.pdf) | [ESP-TM2 User Manual](https://www.rainbird.com/sites/default/files/media/documents/2017-06/man_ESP-TM2_en.pdf) |
| **RC2 / ARC8** | RC2 (`0812`), ARC8 (`0813`) | [RC2 Tech Spec](https://www.rainbird.com/sites/default/files/media/documents/2022-12/d38949heo_rc2_dom_tech_spec.pdf) | [RC2 & ARC8 Manual](https://www.rainbird.com/sites/default/files/media/documents/2022-11/640372-01_04no22_manual_14l_rc2-arc8-web.pdf) |
| **ESP-RZXe** | ESP-RZXe (`0003`), RZXe2 (`0103`) | [ESP-RZXe Tech Spec](https://www.rainbird.com/sites/default/files/media/documents/2018-02/ts_ESP-RZXe_en.pdf) | [ESP-RZXe User Manual](https://www.rainbird.com/sites/default/files/media/documents/2017-06/man_ESP-RZXe_en.pdf) |
| **TBOS-BT** | TBOS-BT (`0099`, `0100`) | [TBOS-BT Tech Spec](https://www.rainbird.com/sites/default/files/media/documents/2018-02/ts_TBOS-BT_en.pdf) | [TBOS-BT Manual](https://www.rainbird.com/sites/default/files/media/documents/2017-06/man_TBOS-BT_en.pdf) |
