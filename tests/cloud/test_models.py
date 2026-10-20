"""Unit tests for Rain Bird cloud integration data models."""

import datetime

import pytest

from pyrainbird.cloud.models import (
    ConnectedData,
    DeviceStateRecord,
    RssiData,
    StationStateData,
)


def test_device_state_record_updated_at_success() -> None:
    """Test updated_at conversion with a valid timestamp."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="test-sk",
        data="{}",
        timestamp=1686700000,
    )
    expected = datetime.datetime.fromtimestamp(1686700000, datetime.UTC)
    assert record.updated_at == expected


def test_device_state_record_updated_at_fallback_ose_overflow_exceptions() -> None:
    """Test updated_at fallback behavior when timestamp parsing raises OSError or OverflowError."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="test-sk",
        data="{}",
        timestamp=2**60,  # Huge value to trigger OSError/OverflowError
    )
    now = datetime.datetime.now(datetime.UTC)
    updated_at = record.updated_at
    # Ensure it fallback-generated a time close to now (within 5 seconds)
    assert abs((updated_at - now).total_seconds()) < 5


def test_device_state_record_updated_at_fallback_value_error_nan() -> None:
    """Test updated_at fallback behavior when timestamp parsing raises ValueError via NaN."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="test-sk",
        data="{}",
        timestamp=float(
            "nan"
        ),  # NaN triggers ValueError: cannot convert float NaN to integer
    )
    now = datetime.datetime.now(datetime.UTC)
    updated_at = record.updated_at
    assert abs((updated_at - now).total_seconds()) < 5


def test_station_state_data_parse_record_success() -> None:
    """Test parsing a valid station state record."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="Station1",
        data='{"state": 1, "remainSec": 30, "programNumber": 2}',
        timestamp=1686700000,
    )
    parsed = StationStateData.parse_record(record)
    assert parsed.state == 1
    assert parsed.remain_sec == 30
    assert parsed.program_number == 2
    assert parsed.is_watering is True


def test_station_state_data_parse_record_no_data_error() -> None:
    """Test StationStateData.parse_record raises ValueError when record data is missing."""
    record = DeviceStateRecord(
        pk="test-pk", sk="Station1", data=None, timestamp=1686700000
    )
    with pytest.raises(ValueError, match="No data found in record"):
        StationStateData.parse_record(record)


def test_station_state_data_parse_record_malformed_json_error() -> None:
    """Test StationStateData.parse_record raises ValueError when record data is malformed JSON."""
    record = DeviceStateRecord(
        pk="test-pk", sk="Station1", data="{invalid_json", timestamp=1686700000
    )
    with pytest.raises(ValueError, match="Failed to parse record data"):
        StationStateData.parse_record(record)


def test_station_state_data_parse_record_epoch_calculation() -> None:
    """Test relative offset subtraction for remain_sec when it holds a unix epoch timestamp."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="Station1",
        data='{"state": 1, "remainSec": 1686700050, "programNumber": 2}',
        timestamp=1686700000,
    )
    parsed = StationStateData.parse_record(record)
    assert parsed.remain_sec == 50  # 1686700050 - 1686700000 = 50


def test_connected_data_parse_record_success() -> None:
    """Test parsing a valid DevicePresence state record."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="DevicePresence",
        data='{"isConnected": true}',
        timestamp=1686700000,
    )
    parsed = ConnectedData.parse_record(record)
    assert parsed.is_connected is True


def test_connected_data_parse_record_disconnected() -> None:
    """Test parsing a disconnected DevicePresence state record."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="DevicePresence",
        data='{"isConnected": false}',
        timestamp=1686700000,
    )
    parsed = ConnectedData.parse_record(record)
    assert parsed.is_connected is False


def test_connected_data_parse_record_non_dict_error() -> None:
    """Test ConnectedData.parse_record raises TypeError when record data is not a JSON object."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="DevicePresence",
        data="0",
        timestamp=1686700000,
    )
    with pytest.raises(TypeError, match="Expected JSON object for DevicePresence"):
        ConnectedData.parse_record(record)


def test_connected_data_parse_record_no_data_error() -> None:
    """Test ConnectedData.parse_record raises ValueError when record data is missing."""
    record = DeviceStateRecord(
        pk="test-pk", sk="DevicePresence", data=None, timestamp=1686700000
    )
    with pytest.raises(ValueError, match="No data found in record"):
        ConnectedData.parse_record(record)


def test_connected_data_parse_record_malformed_json_error() -> None:
    """Test ConnectedData.parse_record raises ValueError when record data is malformed JSON."""
    record = DeviceStateRecord(
        pk="test-pk", sk="DevicePresence", data="{invalid_json", timestamp=1686700000
    )
    with pytest.raises(ValueError, match="Failed to parse record data"):
        ConnectedData.parse_record(record)


def test_rssi_data_parse_record_json_object() -> None:
    """Test parsing RssiData from a JSON object payload."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="RSSI",
        data='{"value": -55}',
        timestamp=1686700000,
    )
    parsed = RssiData.parse_record(record)
    assert parsed.value == -55


def test_rssi_data_parse_record_scalar_int() -> None:
    """Test parsing RssiData from a raw integer payload."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="RSSI",
        data="-82",
        timestamp=1686700000,
    )
    parsed = RssiData.parse_record(record)
    assert parsed.value == -82


def test_rssi_data_parse_record_errors() -> None:
    """Test RssiData.parse_record error handling."""
    with pytest.raises(ValueError, match="No data found in record"):
        RssiData.parse_record(DeviceStateRecord(pk="pk", sk="RSSI", data=None))

    with pytest.raises(ValueError, match="Failed to parse record data"):
        RssiData.parse_record(DeviceStateRecord(pk="pk", sk="RSSI", data="not_json"))

    with pytest.raises(ValueError, match="Invalid RSSI data"):
        RssiData.parse_record(DeviceStateRecord(pk="pk", sk="RSSI", data="true"))
