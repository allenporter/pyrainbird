# RainBird Protocol — LCR Series (RZX / ST8)

> ESP-RZXe (`0003`), ESP-RZXe2 (`0103`), ST8x-WiFi (`0006`), ST8x-WiFi2 (`0008`)
> Verified against companion app v2.17.14 (`RZXSIPProcessing.java`, `ST8SIPProcessing.java`) and physical ESP-RZXe (`0003`, protocol 2.9) hardware captures ([Discussion #611](https://github.com/allenporter/pyrainbird/discussions/611)).

These are **non-program-based** controllers. Unlike ESP-ME/TM2, schedule data is organized **per-zone** rather than per-program. Each zone has its own start times, frequency, and runtime.

---

## Schedule Protocol (Commands `20` / `A0` and `21` / `01`)

### Get Schedule — Request (`20`)

```text
20 00 PP
```
- `20` = `RetrieveScheduleRequest` (3 bytes / 6 hex chars)
- `00` = high byte of 16-bit page parameter
- `PP` = page number (`00` for global controller info, `01`..`08` for zone 1..8 schedule)

### Get Schedule — Response (`A0`)

The response format depends on the page number:

#### Page 0 — Global Rain-Sensor Configuration (`20 00 00`)

Both ESP-RZXe and ST8 return a **4-byte (8 hex character)** response:

```text
A0 00 00 SS
```
- `A0` = `RetrieveScheduleResponse`
- `00 00` = Page 0 echo (`str[2:6] == "0000"`)
- `SS` = Rain-sensor configuration byte (`str[6:8]`), observed on hardware and in the app as `00` or `80`:
  - **Companion App (`RBController.java` → `ST8SIPProcessing.java` / `RZXSIPProcessing.java`)**:
    - All LCR-series controllers (`ESP_RZXe`, `ESP_RZXe2`, `ST8X_WF`, `ST8X_WF2`) use `ST8SIPProcessing`:
      - `SS = 00` (`A0000000`): `isRainSensor = true` (rain sensor **active / obeyed**, not bypassed; `RZXSIPProcessing` checks `intValue() == 0`, `ST8SIPProcessing` checks bit 7 clear)
      - `SS = 80` (`A0000080`): `isRainSensor = false` (rain sensor **bypassed**; bit 7 `0x80` set)
  - **Note ([Discussion #611](https://github.com/allenporter/pyrainbird/discussions/611))**:
    - Physical ESP-RZXe (`0003`, protocol 2.9) confirmed the same 4-byte wire shapes (`A0000000` / `A0000080` on read, `21000000` / `21000080` → `0121` on write), though the reporter labeled `00` as bypassed and `80` as active.

#### Global Rain-Sensor Write (`21 00 00 SS`)

```text
21 00 00 SS    -> 01 21
```
- `21000000` → `0121` (`ST8SIPProcessing.generateGlobalInfoPage()` when `isRainSensor() == true`)
- `21000080` → `0121` (`ST8SIPProcessing.generateGlobalInfoPage()` when `isRainSensor() == false`)

#### Pages 1+ — Per-Zone Schedule Record (`20 00 ZZ`)

Returns a **14-byte (28 hex character)** record:

```text
A0 00 ZZ RR S1 S2 S3 S4 S5 S6 FF DD PP SS
```

| Hex Offset | Byte Index | Field | Size (hex chars) | Description |
|------------|------------|-------|------------------|-------------|
| 0 | 0 | `A0` | 2 | `RetrieveScheduleResponse` code |
| 2 | 1–2 | `00 ZZ` | 4 | Page / Zone number (`0001`..`0008` for zones 1..8) |
| 6 | 3 | `RR` | 2 | **Runtime** in minutes (`00` = zone disabled, `01`..`FF` = minutes) |
| 8–18 | 4–9 | `S1`..`S6` | 12 | **6 Start times**: 1 byte each, stored as `minutesFromMidnight / 10` (`0x00`..`0x8F` = `00:00`..`23:50`). Unused slots are `0x90` (144 → 1440 min) on ESP-RZXe (`0xFF` on some other models) |
| 20 | 10 | `FF` | 2 | **Frequency type** ordinal (`00` = Custom, `01` = Odd, `02` = Even, `03` = Cyclic) |
| 22 | 11 | `DD` | 2 | **Custom days** bitmask (`bit0`=Sun, `bit1`=Mon, `bit2`=Tue, `bit3`=Wed, `bit4`=Thu, `bit5`=Fri, `bit6`=Sat) |
| 24 | 12 | `PP` | 2 | **Cyclic period** in days (`00` or retained previous cyclic period when non-cyclic) |
| 26 | 13 | `SS` | 2 | **Cyclic days remaining (`synchro`) + per-zone sensor flag**: lower 7 bits (`SS & 0x7F`) = days remaining in current cyclic interval; bit 7 (`SS & 0x80`) = per-zone rain sensor flag |

**Frequency Types** (`FF`, in the order the Rain Bird app lists them):
| Value (`FF`) | LCR Meaning | `ProgramFrequency` Enum Mapping |
|--------------|-------------|---------------------------------|
| `00` | CUSTOM (specific days of week) | `ProgramFrequency.CUSTOM` (`0`) |
| `01` | ODD days | `ProgramFrequency.ODD` (`2`) |
| `02` | EVEN days | `ProgramFrequency.EVEN` (`3`) |
| `03` | CYCLIC (every $N$ days) | `ProgramFrequency.CYCLIC` (`1`) |

> **Note on Non-Cyclic Metadata Retention**: When a zone is switched from `CYCLIC` (`03`) to `CUSTOM` (`00`), `ODD` (`01`), or `EVEN` (`02`) in the Rain Bird app, the controller and app retain the previous `PP` (period) and `SS` (synchro/sensor) bytes in the 14-byte record rather than zeroing them out.

---

### Set Per-Zone Schedule — Request (`21`)

Writes a **14-byte (28 hex character)** record and receives a 2-byte ACK (`01 21`):

```text
21 00 ZZ RR S1 S2 S3 S4 S5 S6 FF DD PP SS    -> 01 21
```

| Hex Offset | Field | Size (hex chars) | Description |
|------------|-------|------------------|-------------|
| 0 | `21` | 2 | `SetScheduleRequest` command |
| 2 | `00 ZZ` | 4 | Zone number (`0001`..`0008`, 2 bytes big-endian) |
| 6 | `RR` | 2 | Runtime in minutes (`00` = disabled) |
| 8–18 | `S1`..`S6` | 12 | 6 start times (`minutesFromMidnight / 10`; `90` = unused slot) |
| 20 | `FF` | 2 | Frequency type (`00`=Custom, `01`=Odd, `02`=Even, `03`=Cyclic) |
| 22 | `DD` | 2 | Custom days bitmask |
| 24 | `PP` | 2 | Cyclic days interval |
| 26 | `SS` | 2 | Days remaining (`bits 0..6`) + per-zone sensor flag (`bit 7`) |

#### Hardware-Verified Example (ESP-RZXe `0003`, Protocol 2.9)
- **Read Zone 1** (`20 00 01` → `A000012818909090909000120200`):
  - Zone `01`, Runtime `0x28` (40 min), Start 1 = `0x18` (24 × 10 = 240 min = `04:00`), Starts 2–6 = `0x90` (unused), Frequency `00` (Custom), Days `0x12` (Monday `0x02` + Thursday `0x10`), Retained Period `02`, Synchro/Sensor `00`.
- **Write Zone 1 Runtime 39 min** (`2100012718909090909000120200` → `0121`):
  - Subsequent read (`20 00 01`) returns `A000012718909090909000120200`.

---

## Set Zones Seasonal Adjust Factor (`33`)

RZX/ST8 support per-zone seasonal adjustment (in addition to controller-wide water budget):

```text
33 FF SA1 SA2 SA3 ... SAN
```
- `FF` = zone selector (always `FF` for "all")
- `SA1`–`SAN` = per-station seasonal adjust, 4 hex chars (2 bytes) each, percentage value

---

## Water Budget (`30` / `B0`, `31`)

Despite the per-zone seasonal adjust above, the ESP-RZXe also answers the
water budget commands, with a single controller-wide value:

```text
30 FF          -> B0 FF SSSS
31 FF SSSS     -> 01 31
```
- `FF` = program code. The RZXe replies `NAK 04` (`00 30 04`) for program codes `00`–`08`,
  so `FF` is the only value it accepts.
- `SSSS` = percentage of the programmed runtime, `100` (`0064`) meaning no
  adjustment. The Rain Bird app shows this as -90% to +100%, i.e. `10` (`000A`) to
  `200` (`00C8`).
- Hardware-verified examples:
  - Read 100%: `30 FF` → `B0FF0064`
  - Write 150%: `31 FF 00 96` → `0131`, read-back `30 FF` → `B0FF0096`

---

## Queue Response Parsing (`3B` / `BB`)

Although `RZXSIPProcessing.java` in the legacy Android app does not implement `parseQueue`, **physical ESP-RZXe (`0003`) and ST8 controllers do support `3B`** and return the 10-byte (20 hex character) LCR/ST8 Page 0 format:

```text
3B 00          -> BB 00 QQ AA 00 00 ZZ TT SSSS
```

#### Page 0 — Active Irrigation Status (10 bytes / 20 hex chars)

| Hex Offset | Field | Size (hex chars) | Description |
|------------|-------|------------------|-------------|
| 0–2 | `BB` | 2 | `CurrentQueueResponse` code |
| 2–4 | `page` | 2 | Page number (`00`) |
| 4–6 | `stationsQueued` | 2 | Number of stations queued (`QQ`) |
| 6–8 | `isActiveIrrigation` | 2 | `01` = running, `00` = idle (`AA`) |
| 8–12 | reserved | 4 | `0000` |
| 12–14 | `station` | 2 | Active station number (`ZZ`, `01`..`08`) |
| 14–16 | `irrigationType` | 2 | Irrigation type code (`TT`, e.g. `02` = manual run) |
| 16–20 | `remainingTime` | 4 | Remaining runtime in **seconds** (big-endian `SSSS`) |

#### Hardware-Verified Examples (ESP-RZXe `0003`, Zone 1 manual 10-minute run)
- Immediately after `39 00 01 0A` (`01 39`):
  `3B 00` → `BB000001000001020254` (Zone `01`, type `02`, `0x0254` = **596 seconds** remaining)
- ~2 minutes later:
  `3B 00` → `BB0000010000010201DB` (Zone `01`, type `02`, `0x01DB` = **475 seconds** remaining)

#### Page 1+ — Pending Queue Entries

Entries are packed sequentially:
```text
BB PP [S1 T1 R1R1] [S2 T2 R2R2] ...
```
Where per entry (8 hex chars = 4 bytes):
- `SS` (2 chars) = station number
- `TT` (2 chars) = irrigation type
- `RRRR` (4 chars) = remaining time

---

## Other Hardware-Verified Quirks on ESP-RZXe (`0003`)

- **`0x48` (`CurrentIrrigationStateRequest` → `C8`)**: Can return `C801` (`1`) even when the controller is physically idle (`BF0000000000`), because `0x48` reflects whether the controller is in Automatic/Armed mode rather than whether a zone valve is open. Use `0x3F` (`CurrentStationsActiveRequest` → `BF`) as the authoritative indicator of active watering.
- **`0x05` (`SerialNumberRequest` → `85`)**: Returns `850000000000000000` (serial number `0`).
- **Unsupported Commands (`NAK 01`, `00 <cmd> 01`)**: `0x0B` (Firmware Version), `0x0C` (Universal Message), `0x4A` (Event Timestamp), `0x4B` (Stack Manual Run), `0x4C` (Combined State).

---

## Key Differences from ESP-ME/TM2

| Aspect | LCR (RZX/ST8) | ESP-ME/TM2 |
|--------|---------------|------------|
| Schedule model | Per-zone (`20 00 ZZ` / `21 00 ZZ ...`, 14 bytes) | Per-program |
| Start times per zone | 6 (in 10-minute increments; `0x90` or `0xFF` = unused) | N/A (start times per program) |
| Frequency per zone | Yes (`00`=Custom, `01`=Odd, `02`=Even, `03`=Cyclic) | Per-program (`0`=Custom, `1`=Cyclic, `2`=Odd, `3`=Even) |
| Seasonal adjust | Per-zone (cmd `32`/`B2`) plus controller-wide water budget (`30 FF`/`B0 FF SSSS`) | Per-program (water budget `30 PP`/`B0 PP SSSS`) |
| Rain sensor config | Global page 0 (`20 00 00` → `A0 00 00 SS`, 4 bytes) | Global page 0 (`20 00 00` → `A0 00 00 DD SS BB`, 7 bytes) |
| Queue response (`3B 00`) | 10 bytes (`BB 00 QQ AA 00 00 ZZ TT SSSS`, seconds) | 12 bytes (`BB 00 QQ AA PPPP SS TT MM RRRR`, seconds) |
| Max stations | 6 or 8 | 4–22 depending on model |
