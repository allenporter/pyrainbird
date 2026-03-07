# RainBird Protocol — LCR Series (RZX / ST8)

> ESP-RZXe (`0003`), ESP-RZXe2 (`0103`), ST8x-WiFi (`0006`), ST8x-WiFi2 (`0008`)

These are **non-program-based** controllers. Unlike ESP-ME/TM2, schedule data is organized **per-zone** rather than per-program. Each zone has its own start times, frequency, and runtime.

---

## Schedule Protocol (Commands `20` / `A0`)

### Get Schedule — Request (`20`)

```
20 00 PP
```
- `20` = RetrieveScheduleRequest
- `00` = fixed padding
- `PP` = page number (station number, or `00` for global info)

### Get Schedule — Response (`A0`)

The response format depends on the page number:

#### Page 0 — Global Info

**RZX format** (short response, length < 28 chars):
```
A0 PPPP 00 SS
```
- `SS` = rain sensor state: `00` = sensor enabled, non-zero = sensor bypassed

**ST8 format**:
```
A0 PPPP 00 BB
```
- `BB` = bit field. Bit 7 (`0x80`) = rain sensor bypassed; absent = sensor enabled.

#### Pages 1+ — Per-Station Data

```
A0 PPPP SS RR T1 T2 T3 T4 T5 T6 FF DD CC RR
```

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| 0 | `A0` | 2 | Response code |
| 2 | `PPPP` | 4 | Page identifier (includes station number) |
| 6 | byte 0 | 2 | **Runtime** in minutes (0 = disabled) |
| 8-18 | bytes 1-6 | 12 | **6 Start times**: each 1 byte, value × 10 = minutes from midnight. `0xFF` × 10 = 2550 = OFF |
| 20 | byte 7 | 2 | **Frequency type**: ordinal of `FrequencyType` enum |
| 22 | byte 8 | 2 | **Custom days**: bitmask for days of week |
| 24 | byte 9 | 2 | **Cyclic days**: interval in days |
| 26 | byte 10 | 2 | **Days remaining** + sensor bypass. Bit 7 = sensor bypass flag (1 = bypassed). Lower 7 bits = actual days remaining |

**Frequency Types** (ordinal values):
| Ordinal | Type |
|---------|------|
| 0 | CUSTOM (specific days of week) |
| 1 | CYCLIC (every N days) |
| 2 | ODD days |
| 3 | EVEN days |

**Start time encoding**: Each start time is stored as `minutesFromMidnight / 10`. To decode: `value * 10`. Value `0xFF` (255) means "OFF" (no start time), equivalent to 2550 in decoded form (255 × 10).

---

### Set Schedule — Request (`21`)

```
21 SSSS RR T1 T2 T3 T4 T5 T6 FF DD CC RR
```

| Field | Size | Description |
|-------|------|-------------|
| `21` | 2 | SetSchedule command |
| `SSSS` | 4 | Station number (2 bytes, big-endian) |
| `RR` | 2 | Runtime in minutes (low byte only: `& 0xFF`) |
| T1-T6 | 12 | 6 start times (`minutesFromMidnight / 10`) |
| `FF` | 2 | Frequency type ordinal |
| `DD` | 2 | Custom days bitmask |
| `CC` | 2 | Cyclic days interval |
| `RR` | 2 | Days remaining + sensor bypass (bit 7 = bypass: `OR 0x80` or `AND ~0x80`) |

---

## Set Zones Seasonal Adjust Factor (`33`)

RZX/ST8 use per-zone seasonal adjustment (unlike per-program for ME/TM2):

```
33 FF SA1 SA2 SA3 ... SAN
```
- `FF` = zone selector (always `FF` for "all")
- `SA1`-`SAN` = per-station seasonal adjust, 4 hex chars (2 bytes) each, percentage value



---

## ST8 Global Info Set (`21`)

The ST8 global info page differs from RZX:
```
21 0000 SS
```
- `SS` = `00` = rain sensor enabled, `80` = rain sensor bypassed



---

## Queue Response Parsing

### RZX — No Queue Support

RZX controllers do not support queue queries.

### ST8 — Queue Response (`BB`)

```
BB PP ...
```

#### Page 0 — Active Irrigation Status

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| 2-4 | page | 2 | Page number (0) |
| 4-6 | stationsQueued | 2 | Number of stations queued |
| 6-8 | isActiveIrrigation | 2 | `01` = running, `00` = idle |
| 12-14 | station | 2 | Active station number |
| 14-16 | irrigationType | 2 | Irrigation type code |
| 16-20 | remainingTime | 4 | Remaining runtime (big-endian, minutes) |

#### Page 1+ — Pending Queue Entries

Entries are packed sequentially:
```
BB PP [S1 T1 R1R1] [S2 T2 R2R2] ...
```
Where per entry (8 hex chars = 4 bytes):
- `SS` (2 chars) = station number
- `TT` (2 chars) = irrigation type
- `RRRR` (4 chars) = remaining time

---

## Key Differences from ESP-ME/TM2

| Aspect | LCR (RZX/ST8) | ESP-ME/TM2 |
|--------|---------------|------------|
| Schedule model | Per-zone | Per-program |
| Start times per zone | 6 | N/A (start times per program) |
| Frequency per zone | Yes | Per-program |
| Seasonal adjust | Per-zone (cmd `32`/`B2`) | Per-program (water budget `30`/`B0`) |
| Rain sensor | Global page 0 (bit field) | Global page 0 (byte value) |
| Queue support | ST8 only, RZX returns null | Full support |
| Max stations | 8 | 12-22 depending on model |
