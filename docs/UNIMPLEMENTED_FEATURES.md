# Unimplemented Protocol Features

This document outlines several features defined in the Rain Bird Local Protocol (`sipcommands.yaml`) that have not yet been implemented in the `.async_client` and data processing layers. It defines the necessary adjustments required to fully map these features to Python APIs.

## 1. Stacked Manual Runs (`StackManuallyRunStationRequest`)

**Background:**
Currently, `irrigate_zone` triggers `ManuallyRunStationRequest` (`0x39`). This forcibly overrides the current running program to launch a zone. However, `StackManuallyRunStationRequest` (`0x4B`) allows stacking zones into the execution queue.

**Implementation Guide:**
- **Add to Async Client**: Introduce a method:
  `async def stack_irrigate_zone(self, zone: int, minutes: int) -> None:`
- **Command Structure**: `StackManuallyRunStationRequest` in `sipcommands.yaml` expects a length of `4` with three positional parameters: `page`, `zone`, and `minutes`. Similar to the new `AvailableStationsRequest` logic, you'll need to divide `zone` by 32 to determine the correct page (`page = math.ceil(zone / 32)` or exact index calculation `zone // 32`) or strictly adhere to the position if the command is hardcoded. Let `encode()` handle the parameter packing.
- **Handling Acknowledgement**: This commands relies on a standard `0x01` (Acknowledge) response. You can reuse the existing `True` returning lambda (`lambda resp: True`) inside `_process_command`.

---

## 2. Viewing the Active Execution Queue (`CurrentQueueRequest`)

**Background:**
`CurrentQueueRequest` (`0x3B`) asks the controller what programs or stations are currently queued to run next.

**Implementation Guide:**
- **Paging Requirement**: Just like `CurrentStationsActiveRequest`, this is a paged request. You must supply a `page` parameter at position 2. If the response spans multiple pages, caching execution logic requires looping across the max program/station capacity depending on how the response formats queue data.
- **Data Decoding**: The YAML defines `CurrentQueueResponse` as `"decoder": "decode_queue"`.
- **Modifying Data Converters**: You'll need to implement or verify the `pyrainbird.rainbird.decode_queue` function. Payloads will contain sequences of queued objects (delays, programs, and station IDs). The return object should ideally be a list or custom `data.Queue` class abstracting queued item priority and minutes.

---

## 3. Per-Zone Seasonal Adjustments (`ZonesSeasonalAdjustFactorRequest`)

**Background:**
Instead of retrieving the `seasonalAdjust` for an entire program (which is supported via `0x30`), command `0x32` retrieves exact seasonal adjust data targeted at individual zones.

**Implementation Guide:**
- **Payload Schema**: `ZonesSeasonalAdjustFactorResponse` (`0xB2`) parses 32 bytes (16 pairs) for the `stationsSA` position. A custom array parser in `data.py` (e.g., grouping by 2-byte or 4-byte boundaries according to the protocol) is necessary to iterate across these byte slices.
- **Client Method**: Add `async def get_zone_seasonal_adjust(self, program: int) -> dict[int, int]:` to `async_client.py`.
- **Response Mapping**: The response provides `programCode` and `stationsSA` array. The output should be mapped to a dictionary or mapped array where index equals the station ID, and value equals the percentage (e.g., 100%). It's highly likely that you will need to accommodate multiple controllers fetching multiple pages here if supported.

---

## 4. Controller Event Diagnostics (`ControllerEventTimestampRequest`)

**Background:**
`ControllerEventTimestampRequest` (`0x4A`) pulls the log of device events (power cycles, rain sensor trips, short circuits).

**Implementation Guide:**
- **Payload Schema**: The response `ControllerEventTimestampResponse` (`0xCA`) returns an `eventId` and `timestamp`.
- **Epoch Conversion**: Rain Bird uses epoch offsets. Ensure `timestamp` uses the existing timezone parsing utilities and isn't just displayed as raw 8-byte hex.
- **Client Method**: `async def get_event_timestamp(self, event_type: int) -> datetime:`

---

## 5. Flow Sensor Data (Commands 0x60 - 0x65)

**Background:**
Commented out in `sipcommands.yaml`, these include sequences for triggering Flow learning modules and testing rates.

**Implementation Guide:**
- **Schema Un-commenting**: Uncomment the 6x and Ex series commands.
- **Flow Responses**: The schemas for `FlowMonitorStatusResponse` and `FlowMonitorRateResponse` will need manual validation against the Rain Bird Universal Protocol specifications.
- Typical payloads for Flow Rates return integer values in tenths or hundredths of GPM/LPM. These values will need appropriate division mappings in `pyrainbird/data.py` before surfacing.

---

## 6. High-Capacity Schedule Expansion & Decoding Bounds (Structural Bug)

**Background:**
While core paging support allows dynamic execution, several constraints throughout the API still hard-cap controllers preventing the library from recognizing 40+ program or 60+ station controllers (e.g., LXME2, LX-IVM Pro) properly. The legacy `RetrieveScheduleRequest` mechanism mathematically collapses for devices with more than 15 programs.

**The Bit-Collision Flaw:**
- `get_schedule()` queues legacy command parameters for fetching schedule configurations using binary logic: `0x10 | program` (Program Info) and `0x60 | program` (Start Times). Downstream, `decode_schedule` relies on matching masks (`subcommand & 16 == 16`, `subcommand & 96 == 96`) to isolate the payload typings.
- Legacy parameters max out at 4-bits. For an LXME2 with 40 programs (`max_programs = 40`), program indices greater than 15 will physically break these constraints. E.g., if checking Start Times (`0x60`) for Program 32 (`0x20`), `0x60 + 0x20 = 0x80`.
- `0x80 & 128 == 128` resolves to `True`, meaning `decode_schedule` erroneously parses Program 32's Start Time payload as "Run Times by Zone". This implies legacy SIP command `0x20` cannot fetch schedules for high-capacity controllers without destroying data payload definitions.
- We hypothesize that high-capacity Rain Bird models utilize the newer **Universal (CDT/UPT) Protocol** (`0x0C` Universal Message Requests) for schedule syncs instead of the 1-byte parameter approach used in `0x20`.

**Implementation Guide:**
- **Registry Overhauls:** Several high-end LX-Series controllers map capabilities directly from the legacy ESP-Me. Correct `LX-IVM Pro` → 250 zones, 40 programs; `LX-IVM` → 60 zones.
- **Protocol Transition:** Transition extreme-capacity targets exclusively to Universal Message commands for their schedule retrievals. Ensure `min()` fallback arbitrary caps are removed once decoding scales dynamically.

## Future Research Questions for the App/Protocol Docs

To fully solve the schedule scaling and data limits, please check the decompiled app or Universal Protocol specs for the following:

1. **Scheduling for LX-Series / 2-Wire via CDT:** When the app requests scheduling information for an LX-IVM or LXME2, does it still transmit SIP command `0x20` (and if so, how does it format the parameter?), or does it tunnel schedule requests via `0x0C` (Universal Message)?
2. **RetrieveScheduleResponse Subcommands:** If `0x20` is somehow miraculously still used, what are the new hex boundaries for determining Program Detail vs Start Time vs Run Time when program totals exceed 15?
3. **Queue Payload Format:** For the unimplemented `CurrentQueueRequest` (`0x3B`), how exactly does the app decode the `BB` response? What does the array of delayed/queued programs and stations look like?
4. **Seasonal Adjust Array Dimensions:** Does `ZonesSeasonalAdjustFactorResponse` (`0xB2`) always span exactly 32 stations (16 pairs of bytes), or does the response dynamically scale or require multi-paging depending on the active station count?
