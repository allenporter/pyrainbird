"""Bidirectional state synchronization between CDTStore and UniversalCDTDevice."""

from __future__ import annotations

from typing import Any

from .cdt_schema import get_cdt_default


def sync_cdt_from_device(device: Any) -> None:
    """Synchronize scalar/program fields mutated via SIP commands into cdt_store."""
    n_prog = max(1, device.profile.maximum_programs)
    device.cdt_store["1400"] = device.rain_delay_days
    device.cdt_store["0D00"] = 1 if device.rain_sensor_bypassed else 0
    device.cdt_store["1600"] = [
        device.monthly_water_budget.get(m, 100) for m in range(12)
    ]
    device.cdt_store["1800"] = [device.water_budget.get(p, 100) for p in range(n_prog)]
    if "0C00" not in device.cdt_store:
        device.cdt_store["0C00"] = [device.inter_station_delay_seconds] * n_prog


def sync_device_from_cdt(device: Any, data_id: str) -> None:
    """Synchronize canonical device attributes after a CDT batch write (050B)."""
    stored = device.cdt_store.get(data_id)
    if stored is None:
        return
    if data_id in ("1400", "0D00", "0C00", "1600", "1800"):
        _sync_global_and_adjust(device, data_id, stored)
    elif data_id in ("1300", "1200", "1100", "1000", "0F00", "1D00"):
        _sync_program_schedule(device, data_id, stored)
    elif data_id == "1500" and isinstance(stored, dict):
        _sync_run_times(device, stored)
    elif data_id == "1900" and isinstance(stored, dict):
        _sync_station_sensor_bypass(device, stored)
    elif data_id in ("0A00", "0B00") and isinstance(stored, list):
        _sync_cycle_soak(device, data_id, stored)
    elif data_id in ("0700", "0800", "0900"):
        _sync_calendar_days_off(device)


def _sync_global_and_adjust(device: Any, data_id: str, stored: Any) -> None:
    if data_id == "1400":
        device.rain_delay_days = int(stored)
    elif data_id == "0D00":
        device.rain_sensor_bypassed = int(stored) != 0
    elif data_id == "0C00" and isinstance(stored, list) and stored:
        device.inter_station_delay_seconds = int(stored[0])
    elif data_id == "1600" and isinstance(stored, list):
        for idx, val in enumerate(stored):
            device.monthly_water_budget[idx] = int(val)
    elif data_id == "1800" and isinstance(stored, list):
        for idx, val in enumerate(stored):
            pct = int(val)
            device.water_budget[idx] = pct
            if idx == 0:
                device.seasonal_adjust = pct
            if (idx + 1) in device.programs:
                device.programs[idx + 1].seasonal_adjust = pct


def _sync_program_schedule(device: Any, data_id: str, stored: Any) -> None:
    if data_id in ("1300", "1200", "1100") and isinstance(stored, list):
        for idx, val in enumerate(stored):
            prog = device.programs.get(idx + 1)
            if prog is None:
                continue
            if data_id == "1300":
                prog.water_cycle = int(val)
            elif data_id == "1200":
                prog.cyclic_days = int(val)
            else:
                prog.days_remaining = int(val)
    elif data_id == "1000" and isinstance(stored, dict):
        for p_str, row in stored.items():
            prog = device.programs.get(int(p_str) + 1)
            if prog is not None and isinstance(row, list):
                prog.custom_days_mask = sum(
                    (1 << d) for d, flag in enumerate(row[:7]) if int(flag) != 0
                )
    elif data_id == "0F00" and isinstance(stored, dict):
        for p_str, row in stored.items():
            prog = device.programs.get(int(p_str) + 1)
            if prog is not None and isinstance(row, list):
                prog.permanent_days_off = sum(
                    (1 << d) for d, flag in enumerate(row[:7]) if int(flag) == 0
                )
    elif data_id == "1D00" and isinstance(stored, dict):
        for p_str, row in stored.items():
            prog = device.programs.get(int(p_str) + 1)
            if prog is not None and isinstance(row, list):
                prog.start_times_minutes = [
                    int(v) if 0 <= int(v) < 1440 else 0xFFFF for v in row
                ]


def _sync_run_times(device: Any, stored: dict[str, list[int]]) -> None:
    max_progs = max(1, device.profile.maximum_programs)
    for p_str, row in stored.items():
        p_idx = int(p_str)
        for s_idx, sec in enumerate(row):
            stn = s_idx + 1
            runs = device.station_run_times.setdefault(stn, [0] * max_progs)
            while len(runs) <= p_idx:
                runs.append(0)
            runs[p_idx] = (
                int(sec) if device.profile.is_battery_based else int(sec) // 60
            )


def _sync_station_sensor_bypass(device: Any, stored: dict[str, list[int]]) -> None:
    max_sensors = device.profile.maximum_weather_sensors
    max_stns = device.profile.maximum_stations
    while len(device.station_rain_sensor_obey) < max_stns:
        device.station_rain_sensor_obey.append(True)
    for s_idx in range(max_stns):
        bypassed = False
        for sens_idx in range(max_sensors):
            row = stored.get(str(sens_idx), [])
            if s_idx < len(row) and int(row[s_idx]) != 0:
                bypassed = True
                break
        device.station_rain_sensor_obey[s_idx] = not bypassed


def _sync_cycle_soak(device: Any, data_id: str, stored: list[int]) -> None:
    key = "cycle_seconds" if data_id == "0A00" else "soak_seconds"
    while len(device.station_cycle_soak) < len(stored):
        device.station_cycle_soak.append({"soak_seconds": 0, "cycle_seconds": 0})
    for idx, mins in enumerate(stored):
        device.station_cycle_soak[idx][key] = int(mins) * 60


def _sync_calendar_days_off(device: Any) -> None:
    max_slots = device.profile.maximum_calendar_days_off
    days = device.cdt_store.get("0700", [])
    months = device.cdt_store.get("0800", [])
    years = device.cdt_store.get("0900", [])
    def_day = get_cdt_default(device.profile, "0700")
    while len(device.calendar_days_off) < max_slots:
        device.calendar_days_off.append(None)
    for idx in range(max_slots):
        d = int(days[idx]) if idx < len(days) else def_day
        m0 = int(months[idx]) if idx < len(months) else def_day
        y = int(years[idx]) if idx < len(years) else def_day
        if d == 255 or m0 == 255 or y == 255:
            device.calendar_days_off[idx] = None
        else:
            device.calendar_days_off[idx] = {"month": m0 + 1, "day": d, "year": y}
