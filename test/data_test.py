import unittest

from parameterized import parameterized

from pyrainbird import States


def encode_name_func(testcase_func, param_num, param):
    return "%s_%s_%s" % (
        testcase_func.__name__,
        param_num,
        parameterized.to_safe_name(param.args[0]),
    )


class TestSequence(unittest.TestCase):
    @parameterized.expand(
        [
            ("01", (True,) + (False,) * 7),
            ("02", (False,) + (True,) + (False,) * 6),
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
            ("20000020",
             (False,) * 5 + (True,) + (False,) * 23 + (True,) + (False,) * 2,),
        ],
        name_func=encode_name_func,
    )
    def test_states(self, mask, expected):
        self.assertEqual(expected, States(mask).states)
