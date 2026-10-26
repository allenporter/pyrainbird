"""Model factory and facade for separated Rain Bird device and stick emulators."""

from __future__ import annotations

from typing import Any

from .devices.base import BaseControllerDevice
from .devices.ble import BLEBatteryDevice, SolemTBOSDevice
from .devices.lcr import LCRZoneDevice, ST8ZoneDevice
from .devices.legacy_sip import LegacyProgramDevice, UpgradedTM2Device
from .devices.universal import UniversalCDTDevice
from .profiles import ProtocolFamily, get_controller_profile
from .stick import LNK2StickEmulator

_FAMILY_DEVICE_CLASS_MAP: dict[ProtocolFamily, type[BaseControllerDevice]] = {
    ProtocolFamily.LCR_SIP: LCRZoneDevice,
    ProtocolFamily.LEGACY_PROGRAM_SIP: LegacyProgramDevice,
    ProtocolFamily.UPGRADED_TM2_SIP: UpgradedTM2Device,
    ProtocolFamily.UNIVERSAL_CDT: UniversalCDTDevice,
    ProtocolFamily.BLE_CBOS: BLEBatteryDevice,
    ProtocolFamily.BLE_SOLEM: SolemTBOSDevice,
    ProtocolFamily.GATEWAY: BaseControllerDevice,
}


def get_device_class_for_model(
    model_or_code: str | int,
) -> type[BaseControllerDevice]:
    """Return the separated controller device class for a given model name or SIP code."""
    profile = get_controller_profile(model_or_code)
    if profile.controller_type in ("ST8X_WF", "ST8X_WF2"):
        return ST8ZoneDevice
    if profile.controller_type in ("TBOS_BT", "TBOS_BT_LT"):
        return SolemTBOSDevice
    if profile.controller_type in (
        "ESP_TM2v2",
        "ESP_TM2v3",
        "ESP_TM2v4",
        "TM2R",
        "TRU",
        "ESP_CPTM2",
    ):
        return UpgradedTM2Device
    return _FAMILY_DEVICE_CLASS_MAP.get(profile.protocol_family, BaseControllerDevice)


def create_device_for_model(
    model_or_code: str | int, **kwargs: Any
) -> BaseControllerDevice:
    """Instantiate the concrete separated controller device class for a model."""
    device_cls = get_device_class_for_model(model_or_code)
    return device_cls(model_or_code, **kwargs)


class RainbirdDeviceEmulator:
    """Composable Rain Bird emulator facade pairing LNK2StickEmulator with a concrete controller device."""

    device: BaseControllerDevice
    stick: LNK2StickEmulator

    def __init__(
        self,
        model: str | int,
        *,
        version_major: int = 1,
        version_minor: int = 0,
        password: str | None = None,
        initial_state: dict[str, Any] | None = None,
    ) -> None:
        dev = create_device_for_model(
            model,
            version_major=version_major,
            version_minor=version_minor,
            password=password,
            initial_state=initial_state,
        )
        object.__setattr__(self, "device", dev)
        object.__setattr__(self, "stick", dev.stick)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.device, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if (
            name in ("device", "stick")
            or name in self.__dict__
            or isinstance(getattr(type(self), name, None), property)
        ):
            object.__setattr__(self, name, value)
        else:
            setattr(self.device, name, value)

    @classmethod
    def for_model(cls, model_name: str, **kwargs: Any) -> RainbirdDeviceEmulator:
        """Create an emulator configured for a specific Rain Bird controller model identifier."""
        return cls(model_name, **kwargs)

    @classmethod
    def for_model_code(cls, model_code: int, **kwargs: Any) -> RainbirdDeviceEmulator:
        """Create an emulator configured for a specific 16-bit SIP model code."""
        return cls(model_code, **kwargs)

    def apply_initial_state(self, state: dict[str, Any]) -> None:
        """Configure emulator state from an initial_state dictionary."""
        self.device.apply_initial_state(state)

    def handle_http_post(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Handle simulated HTTP POST to /stick or /stick:80."""
        return self.stick.handle_http_post(*args, **kwargs)

    def handle_jsonrpc(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Dispatch a JSON-RPC 2.0 request to Stick or tunnelSip handlers."""
        return self.stick.handle_jsonrpc(*args, **kwargs)

    def handle_sip(self, payload_hex: str, *, transport: str | None = None) -> str:
        """Execute a raw hexadecimal SIP or Universal (0x0C) command and return hex response."""
        return self.device.handle_sip(payload_hex, transport=transport)

    def handle_universal(self, payload_hex: str) -> str:
        """Dispatch Universal (0x0C / 0x80) messages across subsystems and CDT blocks."""
        if isinstance(self.device, UniversalCDTDevice):
            return self.device.handle_universal(payload_hex)
        raise TypeError(
            f"Model {self.device.profile.controller_type} does not support Universal protocol"
        )

    def handle_gatt_write(
        self, gatt_write_uuid: str, payload_hex: str
    ) -> tuple[str, str]:
        """Handle BLE GATT characteristic writes across CBOS SIP, CBOS OTA, and Solem TBOS-BT."""
        if isinstance(self.device, BLEBatteryDevice):
            return self.device.handle_gatt_write(gatt_write_uuid, payload_hex)
        raise TypeError(
            f"Model {self.device.profile.controller_type} does not support BLE GATT"
        )

    def handle_ble_write(self, write_char: str, payload_hex: str) -> dict[str, str]:
        """Handle BLE GATT write and return {'notify_char': ..., 'payload_hex': ...}."""
        notify_char, resp_hex = self.handle_gatt_write(write_char, payload_hex)
        return {"notify_char": notify_char, "payload_hex": resp_hex}

    def handle_solem_frame(self, payload_hex: str) -> str:
        """Handle Solem [CODE, LENGTH, IT, DATA] BLE frame."""
        if isinstance(self.device, BLEBatteryDevice):
            return self.device.handle_solem_frame(payload_hex)
        raise TypeError(
            f"Model {self.device.profile.controller_type} does not support Solem BLE"
        )
