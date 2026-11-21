# RainBird Protocol — ESP-ME / TM2 Family

> ESP-ME (`0007`), ESP-TM2 (`0005`), ESP-TM2v2 (`000A`), ESP-TM2v3 (`010A`), TM2R (`0014`), TRU (`0015`)

These are **program-based** controllers using **legacy SIP schedule pages**. Schedule data is organized by program, with separate pages for global info, program info, start times, and per-station runtimes.

---

## Device Parameters

| Parameter | ESP-ME | ESP-TM2 | TM2 Upgraded |
|-----------|--------|---------|--------------|
| Max programs | 4 | 3 | 3 |
| Max start times | 6 | 4 | 4 |
| Max stations | 22 | 12 | 12 |
| Runtime pages | 11 | 6 | 6 |

---

## Schedule Protocol (Commands `20` / `A0` / `21`)

### Get Schedule — Request (`20`)

```
20 00 PP
```
- `20` = RetrieveScheduleRequest
- `00` = fixed padding
- `PP` = page number (hex)

### Schedule Page Types

The response code is `A0`. The page number determines the data type:

| Page Range | Type | Per-Device Count |
|------------|------|-----------------|
| `0000` | Global info | 1 |
| `0008` | Cycle & soak per station (optional / supported models) | 1 |
| `0010`-`0013` (16-19) | Program info | 1 per program (max 4) |
| `0020` (32) | Sensor obey/bypass per station | 1 |
| `0040` (64) | Master valve enable per station (optional) | 1 |
| `0060`-`0063` (96-99) | Program start times | 1 per program (max 4) |
| `0080`-`008A` (128-138) | Station runtimes | Variable (ME: 11 pages, TM2: 6 pages; `0084`/`0085` reused for calendar days off on BLE/CBOS/ISK) |

---

### Page 0 (`0000`) — Global Info

**Get response (7 bytes / 14 hex chars on legacy SIP; 9 bytes / 18 hex chars on BLE/CBOS):**
```
A0 0000 DDDD SS RR [MM TT]
```

| Hex Offset | Field | Size (hex chars) | Description |
|------------|-------|-----------------|-------------|
| 0–2 | `A0` | 2 | `RetrieveScheduleResponse` code |
| 2–6 | `page` | 4 | Page ID (`0000`) |
| 6–10 | `interStationDelay` | 4 | Inter-station delay in seconds (`DDDD`, big-endian) |
| 10–12 | `snooze` | 2 | Rain delay / snooze in days (`SS`) |
| 12–14 | `rainSensor` | 2 | `00` = rain sensor enabled (active), `01` = sensor bypassed (`RR`) |
| 14–16 | `masterValveEnable` | 2 | *(BLE/CBOS only)* `01` = master valve enabled, `00` = disabled (`MM`) |
| 16–18 | `rainSettlingTime` | 2 | *(BLE/CBOS only)* Rain settling time in minutes (`TT`) |

**Set command:**
```
21 0000 DDDD SS RR [MM TT]
```
Same field layout as the response data portion (`01 21` ACK).

---

### Page 8 (`0008`) — Per-Station Cycle & Soak (Where Supported)

**Get response / Set payload (after `A0 0008` / `21 0008`):**
```
[SSSS CCCC] × N
```
4 bytes (8 hex chars) per station: `SSSS` = soak duration in seconds (2 bytes big-endian), `CCCC` = cycle duration in seconds (2 bytes big-endian).

---

### Pages 16-19 (`0010`-`0013`) — Program Info

One page per program. Page `0010` = Program 1 (A), `0011` = Program 2 (B), etc.

**Get response (9 bytes / 18 hex chars on legacy SIP):**
```
A0 001P DD CC RR OO SS FF
```
*(Note: BLE/CBOS controllers use an 11-byte / 22-hex-char variant `A0 001P DD CC RR OO SSSS FF AA` with a 2-byte `seasonalAdjust` `SSSS` and trailing `autoRestart` byte `AA`.)*

| Offset (from data start, char 6) | Field | Size (hex chars) | Description |
|----------------------------------|-------|------------------|-------------|
| 0-2 | `customDays` | 2 | Days-of-week bitmask (7 bits: bit 0 = Sun .. bit 6 = Sat; or Mon-Sun per model convention) |
| 2-4 | `cyclicDays` | 2 | Cycle interval in days (`CC`) |
| 4-6 | `daysRemaining` | 2 | Days remaining in current cycle (`RR`) |
| 6-8 | `permanentDaysOff` | 2 | Permanent off-days bitmask (`OO`) |
| 8-10 | `seasonalAdjust` | 2 | Seasonal adjust percentage (`SS`, e.g. `64` = 100%) |
| 10-12 | `frequencyType` | 2 | Frequency type code (`FF`) |

**Set command:**
```
21 001P DD CC RR OO 64 FF
```
Note: the mobile app sets `seasonalAdjust` in Page `001P` to `64` (100%) when writing and adjusts per-program budget via `31 PP SSSS`.

**Frequency Type values:**
| Value | Type |
|-------|------|
| 0 | CUSTOM (days of week) |
| 1 | CYCLIC (every N days) |
| 2 | ODD days |
| 3 | EVEN days |
| 4 | OFF (program disabled, BLE/SIP extensions) |

---

### Pages 32 (`0020`) & 64 (`0040`) — Per-Station Sensor & Master Valve Flags

**Get response (data after `A0 0020` or `A0 0040`):**

Pairs of hex digits (1 byte per station):
```
S1 S2 S3 ... SN
```
- Page `0020`: `01` = rain sensor obeyed for this station, `00` = rain sensor bypassed.
- Page `0040`: `01` = master valve enabled for this station, `00` = disabled.

---

### Pages 96-99 (`60`-`63`) — Program Start Times

One page per program. Page `60` = Program 1 start times, etc.

**Get response (data after `A0 PPPP`):**
```
T1T1 T2T2 T3T3 T4T4 [T5T5 T6T6]
```

Each start time is 4 hex chars (2 bytes) = **minutes from midnight**. Number of start times depends on controller:
- ESP-ME: 6 start times
- ESP-TM2: 4 start times

Value `FFFF` or out-of-range = OFF (no start time).

**Set command:**
```
21 00 PP T1T1 T2T2 T3T3 ...
```
Where `PP` = `60` + (program number - 1).

---

### Pages 128-138 (`80`-`8A`) — Station Runtimes

Each page contains runtimes for **2 stations** across all programs. The page number encodes which station pair:
- Page `80` (128) = Stations 1 & 2
- Page `81` (129) = Stations 3 & 4
- ...
- Page `8A` (138) = Stations 21 & 22

**Page number calculation:**
```
page = floor(station_number / 2) + 128
```

#### Data layout

The data portion contains runtimes organized as:
```
[Station A: P1 P2 P3 P4] [Station B: P1 P2 P3 P4]
```

Each runtime is **4 hex chars** (2 bytes) = minutes.

- Station A = odd station (page * 2 - 255 = first station)
- Station B = even station (Station A + 1)
- Programs repeat for each station: P1, P2, P3, [P4] (ME has 4, TM2 has 3)

**Total data per page**:
- ESP-ME: 4 programs × 2 stations × 4 chars = 32 hex chars
- ESP-TM2: 3 programs × 2 stations × 4 chars = 24 hex chars

**Parsing logic** (from `interpretScheduleResponseString`):
```python
for i in range(0, len(data), 4):
    runtime_hex = data[i:i+4]
    runtime_minutes = int(runtime_hex, 16)
    program_index = (i // 4) % max_programs
    if (i // 4) < max_programs:
        station_number = (page - 128) * 2 + 1  # odd station
    else:
        station_number = (page - 128) * 2 + 2  # even station
```

If runtime > 0, the station is marked as enabled.

---

## Queue Response Parsing (Command `3B` / Response `BB`)

### ESP-TM2 / Legacy ESP-ME Queue (12 bytes / 24 hex chars)

#### Page 0 — Active Irrigation (`3B 00`)

```text
BB 00 MQ AQ RRRR DDDD SS PP FL MV
```
Example: `BB00050005D0000001000001` (5 manual stations queued, `0x05D0` = 1488 seconds remaining on Station 1, Program `00`, MV active `01`); `BB0001000255000001FF0000` (1 manual station running, `0x0255` = 597 s remaining on Station 1, `FF` = manual / no program).

| Hex Offset | Field | Size (hex chars) | Description |
|------------|-------|------------------|-------------|
| 0–2 | `BB` | 2 | `CurrentQueueResponse` code |
| 2–4 | `page` | 2 | Page number (`00`) |
| 4–6 | `manualQueueCount` | 2 | Number of manual queue entries (`MQ`; 2 bytes / 4 hex chars on 14-byte BLE/CBOS queue) |
| 6–8 | `autoQueueCount` | 2 | Number of automatic/program queue entries (`AQ`; 2 bytes / 4 hex chars on 14-byte BLE/CBOS queue) |
| 8–12 | `remainingTime` | 4 | Remaining runtime in **seconds** (big-endian `RRRR`, e.g. `05D0` = 1488 s, `0167` = 359 s) |
| 12–16 | `interStationDelay` | 4 | Remaining inter-station delay in seconds (`DDDD`) |
| 16–18 | `station` | 2 | Active station number (`SS`, `00` = none) |
| 18–20 | `program` | 2 | Active program (`PP`: `01`..`04` for A..D, `FF` = manual / none; app caps values `> maxPrograms` to `0`) |
| 20–22 | `statusFlags` | 2 | Controller queue status flags (`FL`, e.g. bit 3 `0x08` = paused) |
| 22–24 | `masterValve` | 2 | Master valve state (`MV`, `01` = open, `00` = closed) |

**Active irrigation**: `remainingTime > 0 AND (station > 0 OR program > 0)`

#### Page 1+ — Pending Queue Entries (35 bytes / 70 hex chars)

11 entries per page, each 6 hex chars (3 bytes), following `BB PP`:
```text
BB PP [PS1 R1R1] [PS2 R2R2] ... (×11 entries)
```
- `PSi` (2 chars = 1 byte):
  - **Bits 4–0 (`byte & 0x1F`)**: Station number (`1`..`22`; `0` terminates the list — verified in `ESPMESIPProcessing.interpretCurrentQueueResponse`)
  - **Bits 7–5 (`byte >> 5`)**: Program index (`0` = manual, `1`..`4` = Program A..D)
- `RRRR` (4 chars = 2 bytes): Remaining runtime in seconds (big-endian)

### Upgraded TM2 / ME3 Queue (`interpretCurrentQueueResponseME2`)

#### Page 0 — Running State (7 bytes / 14 hex chars)
```text
BB 00 TT SS RRRRRR
```
- `TT` (offset 4–6) = irrigation type (`01` = program, `02` = manual)
- `SS` (offset 6–8) = stations running count

#### Page 1 — Pending Entries (old format, 8 entries × 8 chars)
```text
[PP SS RRRR] ×8
```
- `PP` = program (`01`..`04` for A..D, `05` for manual), `SS` = station, `RRRR` = remaining time in seconds (little-endian / byte-swapped)
- **Byte swap on remaining time**: `((R & 0xFF00) >> 8) | ((R & 0x00FF) << 8)`

#### Page 1 — Pending Entries (new ME3 format, response length = 100 chars)
```text
[PP SS RRRR 0000] ×8
```
12 hex chars per entry (6 bytes), same byte-swap on remaining time.

#### Page 2+ — Simple Pending Entries (17 entries × 4 chars)
```text
[PP SS] ×17
```
- Program and station only, no remaining time.

---

## Hardware-Verified Examples (ESP-TM2 + LNK2, [Discussion #611](https://github.com/allenporter/pyrainbird/discussions/611#discussioncomment-19031360))

| Operation | Request | Response | Decoded Meaning |
|-----------|---------|----------|-----------------|
| Manual run Zone 1 (6 min) | `39 00 01 06` | `01 39` | ACK `ManuallyRunStationRequest` (page `00`, zone `01`, `06` min) |
| Stack manual run Zone 1 (1 min) | `4B 00 01 01` | `01 4B` | ACK `StackManuallyRunStationRequest` (page `00`, zone `01`, `01` min) |
| Stop irrigation | `40` | `01 40` | ACK `StopIrrigationRequest` |
| Current date | `12` | `92 13 A7 EA` | Day `0x13` = 19, Month `0xA` = 10, Year `0x7EA` = 2026 (`2026-10-19`) |
| Current time | `10` | `90 0C 0A 28` | `12:10:40` (`0x0C` = 12, `0x0A` = 10, `0x28` = 40) |
| Active stations (page 0) | `3F 00` | `BF 00 01 00 00 00` | Zone 1 active (`0x01000000` little-endian bitmask) |
| Station errors (pages 0–2) | `3D 00`..`02` | `BD 00 00 00 00 00` | Page `00` echoed, no station errors |
| Water budget (Program A) | `30 00` | `B0 00 00 64` | Program `00` (A), `0x0064` = 100% |
| Combined state / Queue | `4C` / `3B 00` | `CC ...` / `BB ...` | Reports active zone `01` and remaining runtime in **seconds** (`0x0167` = 359 s at start of 6-min run) |

---

## Key Implementation Notes

1. **Station numbering**: Stations are 1-indexed throughout. Station 0 means "none".
2. **Runtime units**: Runtimes in schedule pages (`20`/`A0`, `21`) and manual run commands (`39`, `4B`) are in **minutes**. Remaining runtime in `CurrentQueueResponse` (`BB`) and `CombinedControllerStateResponse` (`CC`) is in **seconds**.
3. **Runtime byte-swapping**: The ME3 queue Page 1 format swaps bytes (little-endian) on queue remaining time fields, whereas the 12-byte TM2/ME Page 0 format (`BB 00 ...`) is big-endian.
4. **Page number mapping**: `floor(station / 2) + 128` for runtime pages. Programs map to pages 16+ and 96+.
5. **Program numbering**: Programs are 1-indexed in the domain model but the page offset uses 0-indexed math (page 16 = program 1, page 96 = program 1).
6. **ESP-TM2 vs ESP-ME**: Only difference in legacy schedule pages is `maxPrograms` (3 vs 4) and `runTimePages` (6 vs 11). All parsing logic is shared between the two families.
