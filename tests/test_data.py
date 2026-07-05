import unittest
from typing import Any

import pytest
from parameterized import parameterized

from pyrainbird.data import States, ModelAndVersion


def encode_name_func(testcase_func, param_num, param):
    return "%s_%s_%s" % (
        testcase_func.__name__,
        param_num,
        parameterized.to_safe_name(param.args[0]),
    )


class TestSequence(unittest.TestCase):
    @parameterized.expand(
        [
            ("01", (False,) * 0 + (True,) + (False,) * 7),
            ("02", (False,) * 1 + (True,) + (False,) * 6),
            ("04", (False,) * 2 + (True,) + (False,) * 5),
            ("08", (False,) * 3 + (True,) + (False,) * 4),
            ("10", (False,) * 4 + (True,) + (False,) * 3),
            ("20", (False,) * 5 + (True,) + (False,) * 2),
            ("40", (False,) * 6 + (True,) + (False,) * 1),
            ("80", (False,) * 7 + (True,) + (False,) * 0),
            ("01000000", (True,) + (False,) * 31),
            ("02000000", (False,) + (True,) + (False,) * 30),
            ("04000000", (False,) * 2 + (True,) + (False,) * 29),
            ("08000000", (False,) * 3 + (True,) + (False,) * 28),
            ("10000000", (False,) * 4 + (True,) + (False,) * 27),
            ("20000000", (False,) * 5 + (True,) + (False,) * 26),
            ("40000000", (False,) * 6 + (True,) + (False,) * 25),
            ("80000000", (False,) * 7 + (True,) + (False,) * 24),
            ("80000080", (False,) * 7 + (True,) + (False,) * 23 + (True,)),
            (
                "40000040",
                (False,) * 6 + (True,) + (False,) * 23 + (True,) + (False,),
            ),
            (
                "20000020",
                (False,) * 5 + (True,) + (False,) * 23 + (True,) + (False,) * 2,
            ),
        ],
        name_func=encode_name_func,
    )
    def test_states(self, mask, expected):
        states = States(mask)
        self.assertEqual(expected, states.states)
        i = 1
        print(states.active_set)
        for bit in expected:
            print(bit)
            active = i in states.active_set
            assert active == bit
            i = i + 1

    def test_update_zone(self) -> None:
        states = States("0000")
        assert not any(states.states)

        # Turn zone 2 on
        states2 = states.update_zone(2, True)
        assert states2.active(2) is True
        assert states2.active_set == {2}
        assert states2.states[1] is True
        assert states2.states[:8] == (
            False,
            True,
            False,
            False,
            False,
            False,
            False,
            False,
        )

        # Turn zone 2 off
        states3 = states2.update_zone(2, False)
        assert states3.active(2) is False
        assert states3.active_set == set()

        # Turn zone 9 on (across byte boundary)
        states4 = states.update_zone(9, True)
        assert states4.active(9) is True
        assert states4.active_set == {9}
        assert states4.states[8] is True


@pytest.mark.parametrize(
    ("response", "expected_name"),
    [
        (
            {"modelID": 2067, "protocolRevisionMajor": 2, "protocolRevisionMinor": 12},
            "ARC8",
        ),
        (
            {"modelID": 9999, "protocolRevisionMajor": 2, "protocolRevisionMinor": 12},
            "Unknown",
        ),
    ],
)
def test_model_info(response: dict[str, Any], expected_name: str) -> None:
    """Test parsing of ModelInfo responses."""
    mv = ModelAndVersion(
        response["modelID"],
        response["protocolRevisionMajor"],
        response["protocolRevisionMinor"],
    )
    assert mv.model_name == expected_name
    assert mv.model_info.name == expected_name
