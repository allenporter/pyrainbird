"""Simulated Rain Bird Wi-Fi stick and irrigation controller emulators.

Conceptual Architecture
-----------------------
A local Rain Bird connection talks to two separate pieces of hardware:

- **The Wi-Fi Stick (`LNK2StickEmulator` in `pyrainbird.testing.stick`)**:
  Handles HTTP, password encryption, and stick-level JSON-RPC settings. For
  irrigation commands, it acts as a serial bridge (`tunnelSip`) forwarding
  binary messages over a small hardware frame buffer to the controller.
- **The Irrigation Controller (`pyrainbird.testing.devices`)**:
  Owns the actual watering state, schedules, sensors, and valves. Hardware
  capabilities and array limits for each model are defined in
  `pyrainbird.testing.catalog` (`ControllerProfile` in `profiles.py`), and
  `RainbirdDeviceEmulator` (`emulator.py`) pairs a stick with the appropriate
  per-family controller device class.
"""

from .device import FakeRainbirdDevice
from .server import RainbirdFakeServer

__all__ = [
    "FakeRainbirdDevice",
    "RainbirdFakeServer",
]
