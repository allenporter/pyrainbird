"""Per-family Rain Bird irrigation controller device emulators.

Conceptual Model: Older vs. Newer ("Universal") Controllers
-----------------------------------------------------------
All Rain Bird controllers share a basic set of commands for simple status and
actions — model ID, clock, active station, rain delay, seasonal adjust, and
starting or stopping manual watering (`BaseControllerDevice` in `base.py`).
They differ primarily in how schedules and extended configuration are modeled:

1. **Older Fixed-Layout Controllers**:
   Used custom, fixed-layout schedule commands tailored to each hardware
   family's limits:
   - `LCRZoneDevice` / `ST8ZoneDevice` (`lcr.py`): Entry-level zone-based
     controllers (`ESP-RZXe*`, `ST8*`) where each zone owns an independent
     schedule.
   - `LegacyProgramDevice` / `UpgradedTM2Device` (`legacy_sip.py`):
     Program-based controllers (`ESP-ME*`, `ESP-TM2*`, `TRU`) where schedules
     are read and written as fixed binary memory pages.
   - `BLEBatteryDevice` / `SolemTBOSDevice` (`ble.py`): Battery-operated
     Bluetooth controllers (`ESP-BAT*`, `TBOS-BT*`) adding BLE GATT transport,
     battery/radio telemetry, and station flow learning.

2. **Newer "Universal" Controllers (`UniversalCDTDevice` in `universal.py`)**:
   Models such as `ARC8`, `RC2`, `ESP-ME3`, `ESP-2WIRE`, `LX-ME2`, and
   `LX-IVM*` keep the basic status/control commands, reject the old
   fixed-layout schedule commands, and replace them with a generic sub-protocol
   split into two parts:
   - **Controller Data Table (CDT) — the "Config Database"**
     (`cdt_store.py`, `cdt_schema.py`): Persistent configuration (program
     frequencies, start times, station runtimes, calendar days off, sensor
     bypasses) lives in numbered tables and N-dimensional arrays. An 8-station
     residential `ARC8` and a 240-station commercial `LX-IVM Pro` speak the
     same schedule protocol; only the array bounds in their profile differ.
   - **Runtime Subsystems — "Live Actions"**
     (`universal.py`, `universal_irrigation.py`, `universal_diagnostics.py`):
     Non-config operations — starting/stopping a program, inspecting the live
     watering queue, setting the clock/timezone, locking the front panel, or
     running 2-wire/module diagnostics — route to small functional subsystems
     alongside the config store.
"""
