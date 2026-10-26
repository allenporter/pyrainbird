"""Unit tests for CDTStore and UniversalCDTDevice."""

from __future__ import annotations

from pyrainbird.testing.devices.cdt_store import CDTStore
from pyrainbird.testing.devices.universal import UniversalCDTDevice


def _uni_pkt(subsys: str, opcode: str, body_hex: str = "") -> str:
    hdr = f"0C20000100080500000000{subsys}000000000005000000"
    length = 2 + len(body_hex) // 2
    len_le = f"{length & 0xFF:02X}{(length >> 8) & 0xFF:02X}"
    return f"{hdr}{len_le}{opcode}{body_hex}"


def test_universal_cdt_batch_and_subsystems() -> None:
    """Verify Universal 0x0C envelope, CDT 0D-3D operations, and subsystems 0x03..0x18."""
    me3 = UniversalCDTDevice("ESP_ME3")
    assert isinstance(me3.cdt_engine, CDTStore)

    # 0D CDT batch write (050B) and read (070B)
    req_set = _uni_pkt("0C", "050B", "021C000001021B00000101")
    resp_set = me3.handle_sip(req_set)
    assert resp_set.endswith("060B00")
    assert me3.cdt_store["1C00"] == 2
    assert me3.cdt_store["1B00"] == 1

    me3.cdt_store["1400"] = 3
    req_get = _uni_pkt("0C", "070B", "01140000")
    resp_get = me3.handle_sip(req_get)
    assert resp_get.endswith("080B01140000020300")

    # 1D, 2D, 3D CDT batch write & read, plus run-length read (1B0B -> 1C0B)
    assert me3.handle_sip(
        _uni_pkt("0C", "050B", "01160001000001000264007800")
    ).endswith("060B00")
    assert "64007800" in me3.handle_sip(_uni_pkt("0C", "070B", "0116000100000100"))
    assert me3.handle_sip(
        _uni_pkt("0C", "050B", "011500020000000000000100045802000058020000")
    ).endswith("060B00")
    assert "58020000" in me3.handle_sip(
        _uni_pkt("0C", "070B", "011500020000000000000100")
    )
    assert me3.handle_sip(
        _uni_pkt("0C", "1B0B", "011500020000000000000100")
    ).startswith("0C20")
    assert me3.handle_sip(
        _uni_pkt("0C", "050B", "011D00030000000000000000000001000268016801")
    ).endswith("060B00")
    assert me3.handle_sip(
        _uni_pkt("0C", "1B0B", "011D0003000000000000000000000100")
    ).startswith("0C20")

    # Subsystem 0x03 (system time): calendar, timezone, SNTP
    assert me3.handle_sip(_uni_pkt("03", "0605", "EA07030F091E00")).endswith("070500")
    assert me3.handle_sip(_uni_pkt("03", "0405")).endswith("0505EA07030F091E00")
    assert me3.handle_sip(_uni_pkt("03", "0905", "5554433000")).endswith("0A0500")
    assert me3.handle_sip(_uni_pkt("03", "0B05")).endswith("0C055554433000")
    assert me3.handle_sip(_uni_pkt("03", "0D05", "01")).endswith("0E0500")
    assert me3.handle_sip(_uni_pkt("03", "0F05")).endswith("100501")

    # Subsystem 0x09 (irrigation control) & 0x13 (controller status & alarms)
    assert me3.handle_sip(_uni_pkt("09", "0A20", "0200")).endswith("0B2000")
    assert me3.handle_sip(_uni_pkt("09", "6620")).startswith("0C20")
    assert me3.handle_sip(_uni_pkt("09", "0C20")).endswith("0D2000")
    assert me3.handle_sip(_uni_pkt("09", "0620")).endswith("072000")
    assert me3.handle_sip(_uni_pkt("09", "2F20")).endswith("302000")
    assert me3.handle_sip("61") == "0161"
    assert me3.handle_sip(_uni_pkt("09", "4E20")).startswith("0C20")
    assert me3.handle_sip(_uni_pkt("09", "5020")).endswith("512000")
    assert me3.handle_sip(_uni_pkt("09", "6420")).startswith("0C20")
    assert me3.handle_sip(_uni_pkt("13", "2D30", "02")).endswith("2E3000")
    assert me3.handle_sip(_uni_pkt("13", "0A30")).endswith("0B30000000")
    me3.alarms = ["NO_WATER_DAYS"]
    assert me3.handle_sip(_uni_pkt("13", "1330")).startswith("0C20")

    # Subsystem 0x18 (panel session), 0x04 (field devices & 2-wire), 0x05/0x0D (modules)
    esp2w = UniversalCDTDevice("ESP_2WIRE")
    assert esp2w.handle_sip(_uni_pkt("09", "4B20", "1E00")).endswith("682000")
    assert esp2w.handle_sip(_uni_pkt("09", "4C20")).endswith("4D201E00")
    req_sess = _uni_pkt("18", "0114", "11223344556677880100")
    assert esp2w.handle_sip(req_sess).endswith(
        f"02141122334455667788{esp2w.session_id}00"
    )
    assert esp2w.front_panel_locked is True
    assert esp2w.handle_sip(_uni_pkt("18", "0714")).endswith("081400")
    assert esp2w.handle_sip(_uni_pkt("18", "0314")).endswith("041400")
    assert esp2w.front_panel_locked is False

    assert esp2w.handle_sip(_uni_pkt("04", "3509", "01")).endswith("360901")
    assert esp2w.handle_sip(_uni_pkt("04", "3709")).startswith("0C20")
    assert esp2w.handle_sip(_uni_pkt("04", "3109", "010001")).endswith("320900")
    assert esp2w.handle_sip(_uni_pkt("04", "3309")).startswith("0C20")
    assert esp2w.handle_sip(_uni_pkt("04", "3B09")).startswith("0C20")
    assert esp2w.handle_sip(_uni_pkt("04", "4C09")).endswith("4D090264")
    assert esp2w.handle_sip(_uni_pkt("04", "2F09")).startswith("0C20")
    assert esp2w.handle_sip(_uni_pkt("04", "2009")).startswith("0C20")
    assert esp2w.handle_sip(_uni_pkt("04", "4E09", "00")).startswith("0C20")
    assert esp2w.handle_sip(_uni_pkt("05", "1F50", "0101")).endswith("205000")
    assert esp2w.handle_sip(_uni_pkt("05", "2350", "02")).endswith("245000")
    assert esp2w.handle_sip(_uni_pkt("05", "2150")).startswith("0C20")
    assert esp2w.handle_sip(_uni_pkt("0D", "240B")).endswith("250B000000000100")
    assert esp2w.handle_sip(_uni_pkt("0D", "220B")).startswith("0C20")
