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
| `00` | Global info | 1 |
| `10`-`13` (16-19) | Program info | 1 per program (max 4) |
| `20` (32) | Sensor bypass per station | 1 |
| `60`-`63` (96-99) | Program start times | 1 per program (max 4) |
| `80`-`8A` (128-138) | Station runtimes | Variable (ME: 11 pages, TM2: 6 pages) |

---

### Page 0 — Global Info

**Get response:**
```
A0 PPPP 00 DDDD SS RR
```

| Offset | Field | Size (hex chars) | Description |
|--------|-------|-----------------|-------------|
| 6 | interStationDelay | 4 | Inter-station delay (hex, in seconds) |
| 10 | snooze | 2 | Rain delay / snooze (days) |
| 12 | rainSensor | 2 | `00` = rain sensor enabled, `01` = sensor bypassed |

**Set command:**
```
21 00 00 DDDD SS RR
```
Same field layout as the response data portion.

---

### Pages 16-19 (`10`-`13`) — Program Info

One page per program. Page `10` = Program 1, `11` = Program 2, etc.

**Get response (data after `A0 PPPP`):**
```
PP DD CC RR OO SS FF
```

| Offset (from data start) | Field | Size | Description |
|--------------------------|-------|------|-------------|
| 0-2 | customDays | 2 | Days-of-week bitmask (7 bits: Sun-Sat) |
| 2-4 | cyclicDays | 2 | Cycle interval in days |
| 4-6 | daysRemaining | 2 | Days remaining in current cycle |
| 6-8 | permanentDaysOff | 2 | Permanent off-days bitmask |
| 8-10 | seasonalAdjust | 2 | Seasonal adjust percentage |
| 10-12 | frequencyType | 2 | Frequency type code |

**Set command:**
```
21 00 PP DD CC RR OO 64 FF
```
Note: seasonal adjust is always set to `64` (100 = 100%) when writing.

**Frequency Type values:**
| Value | Type |
|-------|------|
| 0 | CUSTOM (days of week) |
| 1 | CYCLIC (every N days) |
| 2 | ODD days |
| 3 | EVEN days |

---

### Page 32 (`20`) — Sensor Bypass Per Station

**Get response (data after `A0 PPPP`):**

Pairs of hex digits, one per station:
```
S1 S2 S3 ... SN
```
- `01` = sensor enabled for this station
- `00` = sensor bypassed for this station

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

### Legacy ESP-ME Queue (`interpretCurrentQueueResponse`)

#### Page 0 — Active Irrigation

```
BB 00 .... RRRR .... SS PP ....
```

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| 2-4 | page | 2 | `00` |
| 8-12 | remainingTime | 4 | Remaining time (big-endian, minutes) |
| 16-18 | station | 2 | Active station number |
| 18-20 | program | 2 | Active program number. Capped to maxPrograms |

**Active irrigation**: `remainingTime > 0 AND (station > 0 OR program > 0)`

#### Page 1+ — Pending Queue Entries

11 entries per page, each 6 hex chars (3 bytes):
```
[S1 R1R1] [S2 R2R2] ...
```
- `SS` (2 chars) = station number (masked: `& 0x1F` = lower 5 bits)
- `RRRR` (4 chars) = remaining time
- Entry with station = 0 terminates the list

### Upgraded TM2 / ME3 Queue (`interpretCurrentQueueResponseME2`)

#### Page 0 — Running State
```
BB 00 TT SS
```
- `TT` = irrigation type
- `SS` = stations running count

#### Page 1 — Pending Entries (old format, 8 entries × 8 chars)
```
[PP SS RRRR] ×8
```
- `PP` = program, `SS` = station, `RRRR` = remaining time
- **Byte swap on remaining time**: `((R & 0xFF00) >> 8) | ((R & 0x00FF) << 8)`

#### Page 1 — Pending Entries (new ME3 format, response length = 100 chars)
```
[PP SS RRRR 0000] ×8
```
12 hex chars per entry (6 bytes), same byte-swap on remaining time.

#### Page 2+ — Simple Pending Entries (17 entries × 4 chars)
```
[PP SS] ×17
```
- Program and station only, no remaining time.

---

## Key Implementation Notes

1. **Station numbering**: Stations are 1-indexed throughout. Station 0 means "none".
2. **Runtime units**: All runtimes in schedule pages are in **minutes**. Queue remaining times are also minutes.
3. **Runtime byte-swapping**: The upgraded TM2 family swaps bytes on queue remaining time fields. This is a critical difference from legacy ESP-ME.
4. **Page number mapping**: `floor(station / 2) + 128` for runtime pages. Programs map to pages 16+ and 96+.
5. **Program numbering**: Programs are 1-indexed in the domain model but the page offset uses 0-indexed math (page 16 = program 1, page 96 = program 1).
6. **ESP-TM2 vs ESP-ME**: Only difference is `maxPrograms` (3 vs 4) and `runTimePages` (6 vs 11). All parsing logic is shared between the two families.
