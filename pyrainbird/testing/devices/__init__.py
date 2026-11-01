"""Per-family Rain Bird controller device emulators.

Hardware & Protocol Overview
----------------------------
A networked Rain Bird setup consists of two distinct components:

1. **Wi-Fi Stick (`LNK2StickEmulator` in `pyrainbird.testing.stick`)**:
   Handles HTTP, AES-256-CBC framing, and stick-level JSON-RPC methods, and
   forwards binary SIP commands to the irrigation controller via `tunnelSip`.
2. **Irrigation Controller (`pyrainbird.testing.devices`)**:
   Executes SIP commands to report status, run stations, and store schedules.

Across hardware generations, controllers share a common set of Core SIP status
and manual-control commands (`BaseControllerDevice`) while differing in how
schedules and extended settings are represented:

- `LCRZoneDevice` / `ST8ZoneDevice`: Entry-level zone-based controllers
  (`ESP-RZXe*`, `ST8*`) where each zone stores its own schedule via SIP
  `0x20` / `0x21`.
- `LegacyProgramDevice` / `UpgradedTM2Device`: Program-based controllers
  (`ESP-ME*`, `ESP-TM2*`, `TRU`) that expose schedules as fixed-layout binary
  pages via SIP `0x20` / `0x21`.
- `BLEBatteryDevice` / `SolemTBOSDevice`: Battery-powered Bluetooth controllers
  (`ESP-BAT*`, `TBOS-BT*`) adding BLE GATT characteristics, battery/radio
  telemetry, and station flow learning.
- `UniversalCDTDevice`: Newer controllers (`ARC8`, `RC2`, `ESP-ME3`,
  `ESP-2WIRE`, `LX-ME2`, `LX-IVM*`) that reject legacy `0x20` / `0x21` schedule
  pages and instead tunnel a structured sub-protocol inside SIP opcode `0x0C`
  for runtime subsystems and the Controller Data Table (CDT) config store.
"""
