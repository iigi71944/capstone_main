"""Batch 9: three different positive shapes for three new safe transformer families.

Fixed examples only; subprocess comparisons are not a general security sandbox.
"""
import ast
import subprocess
import sys
import unittest

from app.services.improvement.safe_unmapped_patterns_batch9_service import (
    transform_to_literal_range_style as to_range,
    transform_to_known_membership_style as to_membership,
    transform_to_nested_boolean_style as to_boolean,
)


def observe(src):
    p = subprocess.run([sys.executable, '-I', '-c', src], text=True,
                       capture_output=True, timeout=4, check=False)
    return p.returncode, p.stdout, p.stderr


def positive(test, source, transformer, fragment):
    after = transformer(source)
    test.assertNotEqual(source, after, 'Expected actual transformation')
    test.assertNotEqual(ast.dump(ast.parse(source)), ast.dump(ast.parse(after)))
    test.assertIn(fragment, after)
    before_observation = observe(source)
    test.assertEqual(before_observation[0], 0, before_observation)
    test.assertEqual(observe(after), before_observation)
    test.assertEqual(transformer(after), after, 'Idempotence regression')


class RangeTriplets(unittest.TestCase):
    def test_basic(self):
        positive(self, 'total = 0\nfor n in (0, 1, 2, 3):\n    total += n\nprint(total)\n',
                 to_range, 'range(4)')

    def test_additional(self):
        positive(self, 'values = []\nfor number in [2, 4, 6, 8]:\n    values.append(number * number)\nprint(values)\n',
                 to_range, 'range(2, 10, 2)')

    def test_complex(self):
        positive(self, 'def countdown():\n    output = []\n    for n in (5, 3, 1, -1):\n        output.append(str(n))\n    return ",".join(output)\nprint(countdown())\n',
                 to_range, 'range(5, -3, -2)')


class MembershipTriplets(unittest.TestCase):
    def test_basic(self):
        positive(self, 'x = 2\nif x == 1 or x == 2:\n    print("yes")\nelse:\n    print("no")\n',
                 to_membership, 'x in (1, 2)')

    def test_additional(self):
        positive(self, 'name = "beta"\nif name == "alpha" or name == "beta" or name == "gamma":\n    print("match")\n',
                 to_membership, "name in ('alpha', 'beta', 'gamma')")

    def test_complex(self):
        positive(self, 'def classify():\n    code = -3\n    if code == -1 or code == -3 or code == 7 or code == 99:\n        return "selected"\n    return "other"\nprint(classify())\n',
                 to_membership, 'code in (-1, -3, 7, 99)')


class LogicalTriplets(unittest.TestCase):
    def test_basic(self):
        positive(self, 'a = True\nb = True\nif a:\n    if b:\n        print("both")\n',
                 to_boolean, 'if a and b:')

    def test_additional(self):
        positive(self, 'def score(n):\n    if n > 1:\n        if n < 7:\n            return "mid"\n    return "outside"\nprint(score(4), score(9))\n',
                 to_boolean, 'if n > 1 and n < 7:')

    def test_complex(self):
        positive(self, 'def f(n):\n    if n >= 0:\n        if n % 2 == 0:\n            if n < 100:\n                return "even"\n    return "other"\nprint(f(4), f(101), f(-2))\n',
                 to_boolean, ' and ')


class SkipUnsafeCases(unittest.TestCase):
    def test_range_dynamic_iterable(self):
        s = 'items = [1, 2, 3]\nfor x in items:\n    print(x)\n'
        self.assertEqual(to_range(s), s)

    def test_range_irregular_numbers(self):
        s = 'for x in (1, 2, 5):\n    print(x)\n'
        self.assertEqual(to_range(s), s)

    def test_range_boolean_values(self):
        s = 'for x in (True, 1, 2):\n    print(x)\n'
        self.assertEqual(to_range(s), s)

    def test_range_repeated_value(self):
        s = 'for x in (2, 2, 2):\n    print(x)\n'
        self.assertEqual(to_range(s), s)

    def test_range_shadowing(self):
        s = 'range = lambda *x: []\nfor x in (1, 2, 3):\n    print(x)\n'
        self.assertEqual(to_range(s), s)

    def test_range_unicode(self):
        s = '문구 = []\nfor 숫자 in (1, 2, 3):\n    문구.append(숫자)\nprint(문구)\n'
        positive(self, s, to_range, 'range(1, 4)')

    def test_membership_boolean_type(self):
        s = 'x = True\nif x == 1 or x == 2:\n    print("yes")\n'
        self.assertEqual(to_membership(s), s)

    def test_membership_no_known_binding(self):
        s = 'def f(x):\n    if x == 1 or x == 2:\n        return 4\n'
        self.assertEqual(to_membership(s), s)

    def test_membership_float(self):
        s = 'x = 1.0\nif x == 1 or x == 2:\n    print("yes")\n'
        self.assertEqual(to_membership(s), s)

    def test_membership_mixed_type(self):
        s = 'x = 1\nif x == 1 or x == "1":\n    print("yes")\n'
        self.assertEqual(to_membership(s), s)

    def test_membership_side_effect(self):
        s = 'x = "abc"\nif x.lower() == "a" or x.lower() == "b":\n    print("yes")\n'
        self.assertEqual(to_membership(s), s)

    def test_membership_nonadjacent_binding(self):
        s = 'x = 2\nx = get_value()\nif x == 1 or x == 2:\n    print("yes")\n'
        self.assertEqual(to_membership(s), s)

    def test_logical_if_else(self):
        s = 'if True:\n    if False:\n        print(1)\n    else:\n        print(2)\n'
        self.assertEqual(to_boolean(s), s)

    def test_logical_other_statement(self):
        s = 'if True:\n    print("first")\n    if True:\n        print("second")\n'
        self.assertEqual(to_boolean(s), s)

    def test_logical_single_if(self):
        s = 'if x:\n    print(x)\n'
        self.assertEqual(to_boolean(s), s)

    def test_syntax_invalid_returns_unchanged(self):
        for transform in (to_range, to_membership, to_boolean):
            with self.subTest(transform=transform.__name__):
                self.assertEqual(transform('def f(:\n'), 'def f(:\n')


if __name__ == '__main__':
    unittest.main()
