"""Comprehensive unit tests for Universal CDT controllers, schedules, queues, and wire limits."""

from __future__ import annotations

import struct

import pytest

from pyrainbird.testing.crypto import encode_sip_wire_frame
from pyrainbird.testing.devices.cdt_store import CDTStore
from pyrainbird.testing.devices.universal import UniversalCDTDevice
from pyrainbird.testing.emulator import RainbirdDeviceEmulator

UNIVERSAL_MODELS = (
    "ARC8",
    "RC2",
    "ESP_ME3",
    "ESP_2WIRE",
    "LX_ME2",
    "LX_IVM",
    "LX_IVM_PRO",
)


def _uni_pkt(subsys: str, opcode: str, body_hex: str = "") -> str:
    hdr = f"0C20000100080500000000{subsys}000000000005000000"
    length = 2 + len(body_hex) // 2
    len_le = f"{length & 0xFF:02X}{(length >> 8) & 0xFF:02X}"
    return f"{hdr}{len_le}{opcode}{body_hex}"


def _u16(val: int) -> str:
    return struct.pack("<H", val & 0xFFFF).hex().upper()


def _u32(val: int) -> str:
    return struct.pack("<I", val & 0xFFFFFFFF).hex().upper()


def _get_block(data_id: str, *ranges: tuple[int, int]) -> str:
    rank = len(ranges)
    dims = "".join(f"{_u16(s)}{_u16(e)}" for s, e in ranges)
    return f"{data_id}{rank:02X}{dims}"


def _set_block(
    data_id: str, width: int, payload_hex: str, *ranges: tuple[int, int]
) -> str:
    return f"{_get_block(data_id, *ranges)}{width:02X}{payload_hex}"


def test_universal_cdt_batch_and_subsystems() -> None:
    """Verify Universal 0x0C envelope, CDT 0D-3D operations, and subsystems 0x03..0x18."""
    me3 = UniversalCDTDevice("ESP_ME3")
    assert isinstance(me3.cdt_engine, CDTStore)

    assert me3.handle_sip(_uni_pkt("0C", "050B", "021C000001021B00000101")).endswith(
        "060B00"
    )
    assert me3.cdt_store["1C00"] == 2
    assert me3.cdt_store["1B00"] == 1
    assert me3.handle_sip(_uni_pkt("0C", "010B", "010D00000101")).endswith("020B00")
    assert me3.handle_sip(_uni_pkt("0C", "030B", "010D0000")).endswith(
        "040B010D00000101"
    )

    me3.cdt_store["1400"] = 3
    assert me3.handle_sip(_uni_pkt("0C", "070B", "01140000")).endswith(
        "080B01140000020300"
    )

    assert me3.handle_sip(
        _uni_pkt("0C", "050B", "01160001000001000264007800")
    ).endswith("060B00")
    assert "64007800" in me3.handle_sip(_uni_pkt("0C", "070B", "0116000100000100"))

    assert me3.handle_sip(_uni_pkt("03", "0605", "EA07030F091E00")).endswith("070500")
    assert me3.handle_sip(_uni_pkt("03", "0405")).endswith("0505EA07030F091E00")
    assert me3.handle_sip(_uni_pkt("03", "0905", "5554433000")).endswith("0A0500")
    assert me3.handle_sip(_uni_pkt("03", "0B05")).endswith("0C055554433000")
    assert me3.handle_sip(_uni_pkt("03", "0D05", "01")).endswith("0E0500")
    assert me3.handle_sip(_uni_pkt("03", "0F05")).endswith("100501")
    assert me3.handle_sip(_uni_pkt("09", "2F20")).endswith("302000")
    assert me3.handle_sip("61") == "0161"
    assert me3.handle_sip(_uni_pkt("09", "4E20")).startswith("8C20")
    assert me3.handle_sip(_uni_pkt("09", "5020")).endswith("512000")
    assert me3.handle_sip(_uni_pkt("09", "6420")).startswith("8C20")
    assert me3.handle_sip(_uni_pkt("13", "2D30", "02")).endswith("2E3000")
    assert me3.handle_sip(_uni_pkt("13", "0A30")).endswith("0B30000000")
    me3.alarms = ["NO_WATER_DAYS"]
    assert me3.handle_sip(_uni_pkt("13", "1330")).startswith("8C20")


def test_universal_field_and_module_subsystems() -> None:
    """Verify subsystems 0x18, 0x04, 0x05, and 0x0D on 2-wire Universal controllers."""
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
    assert esp2w.handle_sip(_uni_pkt("04", "3709")).startswith("8C20")
    assert esp2w.handle_sip(_uni_pkt("04", "3109", "010001")).endswith("320900")
    assert esp2w.handle_sip(_uni_pkt("04", "3309")).startswith("8C20")
    assert esp2w.handle_sip(_uni_pkt("04", "3B09")).startswith("8C20")
    assert esp2w.handle_sip(_uni_pkt("04", "4C09")).endswith("4D090264")
    assert esp2w.handle_sip(_uni_pkt("04", "2F09")).startswith("8C20")
    assert esp2w.handle_sip(_uni_pkt("04", "2009")).startswith("8C20")
    assert esp2w.handle_sip(_uni_pkt("04", "4E09", "00")).startswith("8C20")
    assert esp2w.handle_sip(_uni_pkt("05", "1F50", "0101")).endswith("205000")
    assert esp2w.handle_sip(_uni_pkt("05", "2350", "02")).endswith("245000")
    assert esp2w.handle_sip(_uni_pkt("05", "2150")).startswith("8C20")
    assert esp2w.handle_sip(_uni_pkt("0D", "240B")).endswith("250B000000000100")
    assert esp2w.handle_sip(_uni_pkt("0D", "220B")).startswith("8C20")


@pytest.mark.parametrize("model", UNIVERSAL_MODELS)
def test_universal_legacy_schedule_opcodes_rejected(model: str) -> None:
    """Verify legacy SIP 0x20/0x21/0x32/0x33 are unsupported on all Universal controllers."""
    dev = UniversalCDTDevice(model)
    for unsupported_cmd in ("20", "21", "32", "33", "4C"):
        assert dev.handle_sip(f"04{unsupported_cmd}") == f"84{unsupported_cmd}00"
    for supported_cmd in ("02", "03", "0C", "30", "31", "36", "37", "38", "39", "3B"):
        assert dev.handle_sip(f"04{supported_cmd}") == f"84{supported_cmd}01"

    assert dev.handle_sip("200000") == "002001"
    assert dev.handle_sip("200010") == "002001"
    assert dev.handle_sip("200060") == "002001"
    assert dev.handle_sip("200080") == "002001"
    assert dev.handle_sip("21000000000501") == "002101"
    assert dev.handle_sip("3200") == "003201"
    assert dev.handle_sip("33000064") == "003301"


@pytest.mark.parametrize("model", ("ARC8", "RC2", "ESP_ME3", "ESP_2WIRE"))
def test_universal_stack_manual_run_rejected_when_unsupported(model: str) -> None:
    """Verify 0x4B is unsupported on ARC8, RC2, ESP-ME3, and ESP-2WIRE."""
    dev = UniversalCDTDevice(model)
    assert dev.handle_sip("044B") == "844B00"
    assert dev.handle_sip("4B000105") == "004B01"


@pytest.mark.parametrize(
    ("model", "high_stn"),
    [("LX_ME2", 48), ("LX_IVM", 60), ("LX_IVM_PRO", 240)],
)
def test_universal_stack_manual_run_supported_on_lx_models(
    model: str, high_stn: int
) -> None:
    """Verify 0x4B parses 2-byte big-endian station IDs and validates bounds on LX models."""
    dev = UniversalCDTDevice(model)
    assert dev.handle_sip("044B") == "844B01"
    assert dev.handle_sip(f"4B{high_stn:04X}05") == "014B"
    assert dev.active_station == high_stn
    assert dev.remaining_runtime_sec == 300
    over_stn = dev.profile.maximum_stations + 1
    assert dev.handle_sip(f"4B{over_stn:04X}05") == "004B04"


@pytest.mark.parametrize(
    ("model", "exp_cyclic", "max_prog", "max_stn", "max_start"),
    [
        ("ARC8", 3, 3, 8, 4),
        ("RC2", 3, 3, 8, 4),
        ("ESP_ME3", 3, 4, 22, 6),
        ("ESP_2WIRE", 3, 4, 50, 6),
        ("LX_ME2", 1, 40, 48, 10),
        ("LX_IVM", 1, 10, 60, 8),
        ("LX_IVM_PRO", 1, 40, 240, 8),
    ],
)
def test_universal_cdt_factory_defaults_and_run_length_reads(
    model: str, exp_cyclic: int, max_prog: int, max_stn: int, max_start: int
) -> None:
    """Verify factory defaults via 070B and uniform run-length collapsing via 1B0B."""
    dev = UniversalCDTDevice(model)

    req_070b = _uni_pkt(
        "0C",
        "070B",
        "04"
        + _get_block("1400")
        + _get_block("1200", (0, max_prog - 1))
        + _get_block("1800", (0, max_prog - 1))
        + _get_block("1D00", (0, 0), (0, 0), (0, max_start - 1)),
    )
    resp = dev.handle_sip(req_070b)
    cyc_expected = "".join(f"{exp_cyclic:02X}" for _ in range(max_prog))
    adj_expected = "6400" * max_prog
    st_expected = "A005" * max_start
    assert "140000020000" in resp
    assert f"{_get_block('1200', (0, max_prog - 1))}01{cyc_expected}" in resp
    assert f"{_get_block('1800', (0, max_prog - 1))}02{adj_expected}" in resp
    assert (
        f"{_get_block('1D00', (0, 0), (0, 0), (0, max_start - 1))}02{st_expected}"
        in resp
    )

    rle_rt = dev.handle_sip(
        _uni_pkt("0C", "1B0B", "01" + _get_block("1500", (0, 0), (0, max_stn - 1)))
    )
    assert rle_rt.endswith(
        f"1C0B01{_get_block('1500', (0, 0), (0, max_stn - 1))}04000000000000{_u16(max_stn - 1)}"
    )
    rle_st = dev.handle_sip(
        _uni_pkt(
            "0C", "1B0B", "01" + _get_block("1D00", (0, 0), (0, 0), (0, max_start - 1))
        )
    )
    assert rle_st.endswith(
        f"1C0B01{_get_block('1D00', (0, 0), (0, 0), (0, max_start - 1))}02A00500000000{_u16(max_start - 1)}"
    )


@pytest.mark.parametrize("model", UNIVERSAL_MODELS)
@pytest.mark.parametrize("freq_code", (0, 1, 2, 3, 4, 5))
def test_universal_schedule_frequency_start_runtime_roundtrip(
    model: str, freq_code: int
) -> None:
    """Verify full schedule CDT write/read roundtrips and SIP state sync across all models."""
    dev = UniversalCDTDevice(model)
    custom_days = "01000100010000"  # Sun, Tue, Thu (indices 0, 2, 4)
    start_payload = _u16(360) + _u16(1110) + _u16(1440) + _u16(1440)
    rt_payload = _u32(450) + _u32(905)

    set_body = (
        "08"
        + _set_block("1300", 1, f"{freq_code:02X}", (0, 0))
        + _set_block("1000", 1, custom_days, (0, 0), (0, 6))
        + _set_block("1200", 1, "05", (0, 0))
        + _set_block("1100", 1, "02", (0, 0))
        + _set_block("1D00", 2, start_payload, (0, 0), (0, 0), (0, 3))
        + _set_block("1500", 4, rt_payload, (0, 0), (0, 1))
        + _set_block("1800", 2, _u16(125), (0, 0))
        + _set_block("1400", 2, _u16(6))
    )
    assert dev.handle_sip(_uni_pkt("0C", "050B", set_body)).endswith("060B00")

    assert dev.programs[1].water_cycle == freq_code
    assert dev.programs[1].custom_days_mask == 0x15
    assert dev.programs[1].cyclic_days == 5
    assert dev.programs[1].days_remaining == 2
    assert dev.programs[1].start_times_minutes[:4] == [360, 1110, 0xFFFF, 0xFFFF]
    assert dev.handle_sip("36") == "B60006"
    assert dev.handle_sip("3000") == "B000007D"

    get_body = (
        "04"
        + _get_block("1300", (0, 0))
        + _get_block("1000", (0, 0), (0, 6))
        + _get_block("1D00", (0, 0), (0, 0), (0, 3))
        + _get_block("1500", (0, 0), (0, 1))
    )
    get_resp = dev.handle_sip(_uni_pkt("0C", "070B", get_body))
    assert f"{_get_block('1300', (0, 0))}01{freq_code:02X}" in get_resp
    assert f"{_get_block('1000', (0, 0), (0, 6))}01{custom_days}" in get_resp
    assert f"{_get_block('1D00', (0, 0), (0, 0), (0, 3))}02{start_payload}" in get_resp
    assert f"{_get_block('1500', (0, 0), (0, 1))}04{rt_payload}" in get_resp

    # SIP 0x37 and 0x31 mutations propagate back into CDT 1400 and 1800
    assert dev.handle_sip("370009") == "0137"
    assert dev.handle_sip("31000096") == "0131"
    sync_resp = dev.handle_sip(
        _uni_pkt("0C", "070B", "02" + _get_block("1400") + _get_block("1800", (0, 0)))
    )
    assert "140000020900" in sync_resp
    assert f"{_get_block('1800', (0, 0))}029600" in sync_resp


@pytest.mark.parametrize(
    "model", ("ESP_ME3", "ESP_2WIRE", "LX_ME2", "LX_IVM", "LX_IVM_PRO")
)
def test_universal_permanent_days_off_polarity(model: str) -> None:
    """Verify CDT 0F00 Rank-2 factory default (7x 0x01) and inverted day-off polarity."""
    dev = UniversalCDTDevice(model)
    blk = _get_block("0F00", (0, 0), (0, 6))
    init_resp = dev.handle_sip(_uni_pkt("0C", "070B", "01" + blk))
    assert init_resp.endswith(f"080B01{blk}01" + ("01" * 7))

    # Day 0 (Sun) = 0 (Off), Days 1..5 (Mon-Fri) = 1 (Allowed), Day 6 (Sat) = 0 (Off)
    days_payload = "00010101010100"
    assert dev.handle_sip(
        _uni_pkt(
            "0C", "050B", "01" + _set_block("0F00", 1, days_payload, (0, 0), (0, 6))
        )
    ).endswith("060B00")
    assert dev.programs[1].permanent_days_off == 0x41
    read_back = dev.handle_sip(_uni_pkt("0C", "070B", "01" + blk))
    assert read_back.endswith(f"080B01{blk}01{days_payload}")


@pytest.mark.parametrize("model", ("ARC8", "RC2"))
def test_universal_permanent_days_off_unsupported_on_isk(model: str) -> None:
    """Verify CDT 0F00 rejects writes with NAK 0x04 on ARC8 and RC2."""
    dev = UniversalCDTDevice(model)
    resp = dev.handle_sip(
        _uni_pkt("0C", "050B", "01" + _set_block("0F00", 1, "01" * 7, (0, 0), (0, 6)))
    )
    assert resp.endswith("060B04")


@pytest.mark.parametrize(
    ("model", "max_slots"),
    [("LX_ME2", 15), ("LX_IVM", 5), ("LX_IVM_PRO", 5)],
)
def test_universal_calendar_days_off_roundtrip_and_limits(
    model: str, max_slots: int
) -> None:
    """Verify CDT 0700/0800/0900 default to 255 and store valid event-day-off dates."""
    dev = UniversalCDTDevice(model)
    def_resp = dev.handle_sip(
        _uni_pkt("0C", "070B", "01" + _get_block("0800", (0, max_slots - 1)))
    )
    assert def_resp.endswith(
        f"080B01{_get_block('0800', (0, max_slots - 1))}01" + ("FF" * max_slots)
    )

    set_body = (
        "03"
        + _set_block("0700", 1, "04", (0, 0))  # Day = 4
        + _set_block("0800", 1, "06", (0, 0))  # 0-based Month 6 = July
        + _set_block("0900", 2, _u16(2026), (0, 0))  # Year = 2026 (uint16 LE)
    )
    assert dev.handle_sip(_uni_pkt("0C", "050B", set_body)).endswith("060B00")
    assert dev.calendar_days_off[0] == {"year": 2026, "month": 7, "day": 4}

    oob_resp = dev.handle_sip(
        _uni_pkt("0C", "050B", "01" + _set_block("0800", 1, "06", (0, max_slots)))
    )
    assert oob_resp.endswith("060B04")


def test_universal_station_sensor_bypass_1900_1d_and_2d() -> None:
    """Verify CDT 1900 Rank 2 sensor-station bypass single-row and multi-sensor bit-packing."""
    me3 = UniversalCDTDevice("ESP_ME3")
    assert me3.handle_sip(
        _uni_pkt("0C", "050B", "01" + _set_block("1900", 1, "010001", (0, 0), (0, 2)))
    ).endswith("060B00")
    assert me3.station_rain_sensor_obey[:3] == [False, True, False]
    row_resp = me3.handle_sip(
        _uni_pkt("0C", "070B", "01" + _get_block("1900", (0, 0), (0, 2)))
    )
    assert row_resp.endswith(f"080B01{_get_block('1900', (0, 0), (0, 2))}01010001")

    ivm = UniversalCDTDevice("LX_IVM")
    # 2 weather sensors (0..1) x 3 stations (0..2): sensor 0=[1, 0, 1], sensor 1=[0, 1, 1]
    assert ivm.handle_sip(
        _uni_pkt(
            "0C",
            "050B",
            "01" + _set_block("1900", 1, "010001000101", (0, 1), (0, 2)),
        )
    ).endswith("060B00")
    # Multi-sensor read packs sensor bits per station: stn0=0b01(01), stn1=0b10(02), stn2=0b11(03)
    packed_resp = ivm.handle_sip(
        _uni_pkt("0C", "070B", "01" + _get_block("1900", (0, 1), (0, 2)))
    )
    assert packed_resp.endswith(f"080B01{_get_block('1900', (0, 1), (0, 2))}01010203")


@pytest.mark.parametrize("model", UNIVERSAL_MODELS)
def test_universal_cdt_index_bounds(model: str) -> None:
    """Verify per-profile index bounds return 060B04 on write and width 00 on read."""
    dev = UniversalCDTDevice(model)
    p = dev.profile

    assert dev.handle_sip(
        _uni_pkt(
            "0C", "050B", "01" + _set_block("1300", 1, "00", (0, p.maximum_programs))
        )
    ).endswith("060B04")
    assert dev.handle_sip(
        _uni_pkt(
            "0C",
            "050B",
            "01" + _set_block("1500", 4, _u32(60), (0, 0), (0, p.maximum_stations)),
        )
    ).endswith("060B04")
    assert dev.handle_sip(
        _uni_pkt(
            "0C",
            "050B",
            "01"
            + _set_block(
                "1D00", 2, _u16(360), (0, 0), (0, 0), (0, p.maximum_start_times)
            ),
        )
    ).endswith("060B04")
    oob_get = dev.handle_sip(
        _uni_pkt("0C", "070B", "01" + _get_block("1300", (0, p.maximum_programs)))
    )
    assert oob_get.endswith(f"080B01{_get_block('1300', (0, p.maximum_programs))}00")


@pytest.mark.parametrize("model", UNIVERSAL_MODELS)
def test_universal_cdt_nak_codes_and_atomic_rollback(model: str) -> None:
    """Verify NAK codes 01/02/03/05 and atomic multi-block 050B rollback."""
    dev = UniversalCDTDevice(model)
    p = dev.profile

    assert dev.handle_sip(_uni_pkt("0C", "050B", "01FF99000100")).endswith("060B03")
    assert dev.handle_sip(
        _uni_pkt("0C", "050B", "01" + _set_block("1400", 2, "0100", (0, 0)))
    ).endswith("060B02")
    assert dev.handle_sip(
        _uni_pkt("0C", "050B", "01" + _set_block("1500", 1, "3C", (0, 0), (0, 0)))
    ).endswith("060B05")
    assert dev.handle_sip(
        _uni_pkt(
            "0C",
            "050B",
            "01" + _set_block("1D00", 2, _u16(1441), (0, 0), (0, 0), (0, 0)),
        )
    ).endswith("060B01")
    assert dev.handle_sip(
        _uni_pkt(
            "0C",
            "050B",
            "01"
            + _set_block("0C00", 2, _u16(p.maximum_station_delay_seconds + 1), (0, 0)),
        )
    ).endswith("060B01")

    atomic_body = (
        "02"
        + _set_block("1400", 2, _u16(11))
        + _set_block("1300", 1, "09", (0, 0))  # 9 > max frequency code 5 -> NAK 01
    )
    assert dev.handle_sip(_uni_pkt("0C", "050B", atomic_body)).endswith("060B01")
    assert dev.rain_delay_days == 0
    assert "1400" not in dev.cdt_store
    assert dev.handle_sip(
        _uni_pkt("0C", "050B", "01" + _set_block("1200", 1, "00", (0, 0)))
    ).endswith("060B00")


def test_universal_program_and_manual_irrigation_queue_execution() -> None:
    """Verify 0A20, 0220, 0x38, 6620->6720, 0x3B (pages 0..2), 0x3F, advance, and stop."""
    rc2 = UniversalCDTDevice("RC2")

    # Configure Program A: Station 1 = 45s (sub-minute), Station 3 = 600s, Adjust = 150% -> 68s, 900s
    cfg = (
        "02"
        + _set_block("1500", 4, _u32(45) + _u32(0) + _u32(600), (0, 0), (0, 2))
        + _set_block("1800", 2, _u16(150), (0, 0))
    )
    assert rc2.handle_sip(_uni_pkt("0C", "050B", cfg)).endswith("060B00")
    assert rc2.handle_sip(_uni_pkt("09", "0A20", "0205")).endswith("010004")

    assert rc2.handle_sip(_uni_pkt("09", "0A20", "0200")).endswith("0B2000")
    assert rc2.handle_sip("3F00") == "BF0001000000"
    assert rc2.handle_sip("3B00") == "BB000201020000"
    q1 = rc2.handle_sip("3B01")
    assert len(q1) == 68
    assert q1.startswith(f"BB010101{_u16(68)}")
    q2 = rc2.handle_sip("3B02")
    assert len(q2) == 100
    assert q2.startswith(f"BB020103{_u16(900)}0000")

    q_uni = rc2.handle_sip(_uni_pkt("09", "6620", "00"))
    rec0 = struct.pack("<HBBBII", 0, 2, 0, 6, 68, 0).hex().upper()
    rec1 = struct.pack("<HBBBII", 2, 1, 0, 6, 900, 0).hex().upper()
    assert q_uni.endswith(f"6720000002{rec0}{rec1}")

    # Advance via 0C20 -> Station 3 becomes Cycling
    assert rc2.handle_sip(_uni_pkt("09", "0C20")).endswith("0D2000")
    assert rc2.handle_sip("3F00") == "BF0004000000"
    assert rc2.remaining_runtime_sec == 900

    # Stop via 0620 -> Idle
    assert rc2.handle_sip(_uni_pkt("09", "0620")).endswith("072000")
    assert rc2.handle_sip("3F00") == "BF0000000000"
    assert rc2.handle_sip("3B00") == "BB000000000000"

    # SIP 0x38 manual program run and 0220 manual station run
    assert rc2.handle_sip("3800") == "0138"
    assert rc2.active_station == 1
    assert rc2.remaining_runtime_sec == 68
    assert rc2.handle_sip("4200") == "0142"
    assert rc2.active_station == 3
    assert rc2.handle_sip("40") == "0140"
    assert rc2.active_station == 0

    assert rc2.handle_sip(_uni_pkt("09", "0220", f"01{_u16(1)}{_u32(180)}")).endswith(
        "032000"
    )
    assert rc2.active_station == 2
    assert rc2.remaining_runtime_sec == 180
    assert rc2.handle_sip(_uni_pkt("09", "0420", _u16(1))).endswith("052000")
    assert rc2.active_station == 0


def test_sip_wire_frame_and_universal_envelope_length_limits() -> None:
    """Verify <= 255-byte raw SIP wire frame limit and Universal 0x0C length checks."""
    frame_255 = encode_sip_wire_frame(b"\x02" * 255)
    assert frame_255[0] == 0xF5
    with pytest.raises(ValueError, match="255 bytes"):
        encode_sip_wire_frame(b"\x02" * 256)

    emu = RainbirdDeviceEmulator.for_model("ESP_ME3")
    oversize_hex = "0C" + ("00" * 255)  # 256 bytes -> exceeds 1-byte wire length
    rpc_resp = emu.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tunnelSip",
            "params": {"data": oversize_hex, "length": 256},
        }
    )
    assert rpc_resp["error"]["code"] == -32602
    assert emu.device.handle_sip(oversize_hex) == "000C02"

    # Malformed Universal 0x0C envelope with mismatched declared payload length
    bad_uni = "0C200001000805000000000C0000000000050000000900070B01140000"
    assert emu.device.handle_sip(bad_uni) == "000C02"
