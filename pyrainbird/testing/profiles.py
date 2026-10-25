"""Device capability catalog and controller profiles for Rain Bird controllers."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import yaml
from mashumaro import field_options
from mashumaro.mixins.yaml import DataClassYAMLMixin


class ProtocolFamily(StrEnum):
    """Protocol family classification for Rain Bird controllers."""

    LCR_SIP = "LCR_SIP"
    LEGACY_PROGRAM_SIP = "LEGACY_PROGRAM_SIP"
    UPGRADED_TM2_SIP = "UPGRADED_TM2_SIP"
    UNIVERSAL_CDT = "UNIVERSAL_CDT"
    BLE_CBOS = "BLE_CBOS"
    BLE_SOLEM = "BLE_SOLEM"
    GATEWAY = "GATEWAY"


CONTROLLER_TYPE_ORDINAL_ORDER: tuple[str, ...] = (
    "ESP_RZXe",
    "ESP_RZXe2",
    "ESP_ME",
    "ESP_MEv2",
    "ESP_TM2",
    "ESP_ME3",
    "ESP_2WIRE",
    "ESP_TM2v2",
    "ESP_TM2v3",
    "ESP_TM2v4",
    "TM2R",
    "LX_ME2",
    "LX_IVM",
    "LX_IVM_PRO",
    "ST8X_WF",
    "ST8X_WF2",
    "RC2",
    "ARC8",
    "TRU",
    "ESP_CPTM2",
    "ESP_BAT_BT",
    "ESP_BAT_BT_2",
    "ESP_BAT_BT_4",
    "ESP_BAT_BT_6",
    "TBOS_BT",
    "TBOS_BT_LT",
    "ESP_BAT_PRO",
    "ESP_BAT_PRO_EU",
    "ESP_BAT_PRO_FLOW",
    "ESP_BAT_PRO_FLOW_EU",
    "IQ_GATEWAY",
)


@dataclass(frozen=True)
class ControllerProfile(DataClassYAMLMixin):
    """Hardware capability and protocol profile for a Rain Bird controller."""

    controller_type: str
    controller_name: str
    sip_model: int
    sip_model_hex: str
    wire_model_hex: str
    protocol_family: ProtocolFamily = field(
        metadata=field_options(deserialize=ProtocolFamily)
    )
    program_based: bool
    seconds_based: bool
    serial_number: bool
    maximum_programs: int
    maximum_stations: int
    maximum_start_times: int
    maximum_sensors: int
    maximum_available_stations_pages: int
    maximum_rain_delay_days: int
    maximum_manual_run_seconds: int
    maximum_run_time_seconds: int
    maximum_seasonal_adjust: int
    minimum_seasonal_adjust: int
    schedule_timestamp: bool
    universal_messages: bool
    cycle_and_soak: bool
    posix_time_zone: bool
    global_seasonal_adjustment: bool
    controller_state_set: bool
    combined_controller_state: bool
    stack_manual_run_station: bool
    master_valves_settings: bool = False
    is_battery_based: bool = False
    is_in_lcr_series: bool = False
    is_cbos_series: bool = False
    is_isk_controller: bool = False
    is_lx_controller: bool = False
    is_tm2: bool = False
    is_upgraded_tm2: bool = False

    @property
    def is_universal_based(self) -> bool:
        """Return True if controller uses Universal CDT/UPT protocol (0x0C/0x8C)."""
        return self.universal_messages

    @property
    def is_universal_protocol(self) -> bool:
        """Alias for is_universal_based."""
        return self.universal_messages

    @property
    def is_isk_series(self) -> bool:
        """Alias for is_isk_controller."""
        return self.is_isk_controller

    @property
    def is_lcr(self) -> bool:
        """Alias for is_in_lcr_series."""
        return self.is_in_lcr_series

    @property
    def is_battery_powered(self) -> bool:
        """Alias for is_battery_based."""
        return self.is_battery_based


def _load_device_profiles() -> dict[str, ControllerProfile]:
    """Load all per-controller YAML profile files from the catalog directory."""
    catalog_dir = Path(__file__).parent / "catalog"
    profiles: dict[str, ControllerProfile] = {}
    for path in sorted(catalog_dir.glob("*.yaml")):
        prof = ControllerProfile.from_yaml(
            path.read_text(encoding="utf-8"), decoder=yaml.safe_load
        )
        profiles[prof.controller_type] = prof
    return profiles


DEVICE_PROFILES: dict[str, ControllerProfile] = _load_device_profiles()

MANUFACTURING_DEVICE_MODEL_MAP: dict[str, str] = {
    "0020": "ESP_BAT_PRO",
    "0021": "ESP_BAT_PRO_EU",
    "0022": "ESP_BAT_PRO_FLOW",
    "0023": "ESP_BAT_PRO_FLOW_EU",
}

MODEL_ALIASES: dict[str, str] = {
    "ARC": "ARC8",
    "LXME2": "LX_ME2",
    "LXIVM": "LX_IVM",
    "TRU_2": "TRU",
    "ESP-RZXe": "ESP_RZXe",
    "ESP-ME": "ESP_ME",
    "ESP-Me": "ESP_ME",
    "ESP-TM2": "ESP_TM2",
    "ESP-ME3": "ESP_ME3",
    "ESP-2Wire": "ESP_2WIRE",
    "ST8x-WiFi": "ST8X_WF",
    "ST8x-WiFi2": "ST8X_WF2",
    "LX-IVM": "LX_IVM",
    "LX-IVM Pro": "LX_IVM_PRO",
    "BAT-BT": "ESP_BAT_BT",
    "TBOS-BT": "TBOS_BT",
    "BAT-PRO": "ESP_BAT_PRO",
    "BAT-PRO Flow": "ESP_BAT_PRO_FLOW",
    "IQ Gateway": "IQ_GATEWAY",
    "0099": "TBOS_BT",
    "0100": "TBOS_BT_LT",
    "0107": "ESP_MEv2",
}


def resolve_controller_type_from_model_id(
    model_id_hex: str | int, *, include_manufacturing: bool = True
) -> str | None:
    """Resolve controller model identifier from 4-char SIP model hex or manufacturing fallback."""
    if isinstance(model_id_hex, int):
        normalized = "-0001" if model_id_hex in (-1, 0xFFFF) else f"{model_id_hex:04X}"
    else:
        normalized = model_id_hex.strip().upper()
    if normalized == "FFFF":
        normalized = "-0001"
    for enum_name in CONTROLLER_TYPE_ORDINAL_ORDER:
        prof = DEVICE_PROFILES[enum_name]
        if prof.sip_model_hex.upper() == normalized:
            return enum_name
    if include_manufacturing and normalized in MANUFACTURING_DEVICE_MODEL_MAP:
        return MANUFACTURING_DEVICE_MODEL_MAP[normalized]
    return None


def get_controller_profile(model_or_code: str | int) -> ControllerProfile:
    """Lookup a ControllerProfile by model identifier, display name, or SIP model code."""
    if isinstance(model_or_code, int):
        hex_code = "-0001" if model_or_code in (-1, 0xFFFF) else f"{model_or_code:04X}"
        resolved = resolve_controller_type_from_model_id(hex_code)
        if resolved:
            return DEVICE_PROFILES[resolved]
        raise ValueError(f"Unknown model code: {model_or_code:#x}")

    key = model_or_code.strip()
    if key in DEVICE_PROFILES:
        return DEVICE_PROFILES[key]
    if key in MODEL_ALIASES:
        return DEVICE_PROFILES[MODEL_ALIASES[key]]
    upper = key.upper().removeprefix("0X")
    if len(upper) <= 4 and all(c in "0123456789ABCDEF" for c in upper.lstrip("-")):
        padded = "-0001" if upper in ("-1", "-0001", "FFFF") else upper.zfill(4)
        resolved = resolve_controller_type_from_model_id(padded)
        if resolved:
            return DEVICE_PROFILES[resolved]
    for prof in DEVICE_PROFILES.values():
        if (
            prof.controller_name.lower() == key.lower()
            or prof.controller_type.lower() == key.lower()
        ):
            return prof
    raise ValueError(f"Unknown controller model identifier: {model_or_code!r}")


__all__ = [
    "CONTROLLER_TYPE_ORDINAL_ORDER",
    "ControllerProfile",
    "DEVICE_PROFILES",
    "MANUFACTURING_DEVICE_MODEL_MAP",
    "MODEL_ALIASES",
    "ProtocolFamily",
    "get_controller_profile",
    "resolve_controller_type_from_model_id",
]
