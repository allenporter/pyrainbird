"""Unit tests for device capability catalog and controller profiles."""

from __future__ import annotations

import pytest

from pyrainbird.testing.profiles import (
    CONTROLLER_TYPE_ORDINAL_ORDER,
    DEVICE_PROFILES,
    MANUFACTURING_DEVICE_MODEL_MAP,
    ControllerProfile,
    ProtocolFamily,
    get_controller_profile,
    resolve_controller_type_from_model_id,
)


def test_all_31_controller_profiles_present() -> None:
    """Verify all 31 controller model entries exist in DEVICE_PROFILES with valid limits."""
    assert len(CONTROLLER_TYPE_ORDINAL_ORDER) == 31
    for model_name in CONTROLLER_TYPE_ORDINAL_ORDER:
        assert model_name in DEVICE_PROFILES
        prof = get_controller_profile(model_name)
        assert isinstance(prof, ControllerProfile)
        assert prof.controller_type == model_name
        assert prof.maximum_stations >= 0
        assert isinstance(prof.protocol_family, ProtocolFamily)


def test_model_id_resolution_and_manufacturing_fallbacks() -> None:
    """Verify SIP model hex resolution and manufacturing fallbacks."""
    assert resolve_controller_type_from_model_id("0009") == "ESP_ME3"
    assert resolve_controller_type_from_model_id(0x010A) == "ESP_TM2v3"
    assert resolve_controller_type_from_model_id("0020") == "ESP_BAT_PRO"
    assert resolve_controller_type_from_model_id("0023") == "ESP_BAT_PRO_FLOW_EU"
    assert (
        resolve_controller_type_from_model_id("0020", include_manufacturing=False)
        is None
    )
    assert resolve_controller_type_from_model_id("-0001") == "IQ_GATEWAY"
    # Integer model IDs format as 16-bit hex, so -1 becomes "FFFF" and
    # does not match IQ_GATEWAY's "-0001" sip_model_hex.
    assert resolve_controller_type_from_model_id("FFFF") is None
    assert resolve_controller_type_from_model_id(-1) is None
    # Shared definitions resolve to the first enum entry.
    assert resolve_controller_type_from_model_id("0007") == "ESP_ME"
    assert resolve_controller_type_from_model_id("000B") == "ESP_BAT_BT"
    assert MANUFACTURING_DEVICE_MODEL_MAP["0021"] == "ESP_BAT_PRO_EU"


def test_series_groupings_and_classifications() -> None:
    """Verify Universal vs Legacy SIP, ISK, LCR, Upgraded TM2, and Battery series flags."""
    me3 = get_controller_profile("ESP_ME3")
    assert me3.is_universal_based is True
    assert me3.is_universal_protocol is True
    assert me3.protocol_family == ProtocolFamily.UNIVERSAL_CDT

    tm2v3 = get_controller_profile("ESP_TM2v3")
    assert tm2v3.is_universal_protocol is False
    assert tm2v3.is_upgraded_tm2 is True
    assert tm2v3.is_tm2 is True
    assert tm2v3.protocol_family == ProtocolFamily.UPGRADED_TM2_SIP

    rc2 = get_controller_profile("RC2")
    assert rc2.is_universal_protocol is True
    assert rc2.is_isk_series is True

    rzxe = get_controller_profile("ESP_RZXe")
    assert rzxe.is_lcr is True
    assert rzxe.protocol_family == ProtocolFamily.LCR_SIP

    bat_pro = get_controller_profile("ESP_BAT_PRO")
    assert bat_pro.is_battery_powered is True
    assert bat_pro.is_cbos_series is True
    assert bat_pro.protocol_family == ProtocolFamily.BLE_CBOS

    # Station count is overridden per BAT-BT variant.
    assert [
        get_controller_profile(name).maximum_stations
        for name in ("ESP_BAT_BT", "ESP_BAT_BT_2", "ESP_BAT_BT_4", "ESP_BAT_BT_6")
    ] == [1, 2, 4, 6]

    # TBOS is not part of the BAT-BT/BAT-PRO battery series.
    tbos = get_controller_profile("TBOS_BT")
    assert tbos.is_battery_powered is False
    assert tbos.is_cbos_series is False

    lx_ivm = get_controller_profile("LX_IVM")
    assert lx_ivm.is_lx_controller is True
    assert lx_ivm.master_valves_settings is True


def test_lookup_aliases_and_unknown_error() -> None:
    """Verify get_controller_profile supports display names, hex strings, and ints."""
    assert get_controller_profile("ESP-ME3").controller_type == "ESP_ME3"
    assert get_controller_profile("esp-me3").controller_type == "ESP_ME3"
    assert get_controller_profile("esp_me3").controller_type == "ESP_ME3"
    assert get_controller_profile(0x0005).controller_type == "ESP_TM2"
    assert get_controller_profile("-1").controller_type == "IQ_GATEWAY"
    assert get_controller_profile("0011").controller_type == "ESP_2WIRE"
    with pytest.raises(ValueError, match="Unknown model code"):
        get_controller_profile(-1)
    for unknown_id in ("0099", "0100", "0107"):
        with pytest.raises(ValueError, match="Unknown"):
            get_controller_profile(unknown_id)
    assert resolve_controller_type_from_model_id("9999") is None
    with pytest.raises(ValueError, match="Unknown model code"):
        get_controller_profile(0x9999)
    with pytest.raises(ValueError, match="Unknown"):
        get_controller_profile("9999")
    with pytest.raises(ValueError, match="Unknown"):
        get_controller_profile("NON_EXISTENT_MODEL")
