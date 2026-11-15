"""Batch 13 constrained positive triplets and negative/safety tests."""
from __future__ import annotations

import ast
import unittest

from app.services.improvement.safe_unmapped_patterns_batch13_service import (
    transform_to_safe_string_literal_style as string_style,
    transform_to_safe_number_literal_style as number_style,
    transform_to_safe_boolean_literal_style as boolean_style,
)


def _check(test: unittest.TestCase, original: str, transform, expected: str) -> None:
    changed = transform(original)
    test.assertEqual(changed, expected)
    ast.parse(changed)
    test.assertEqual(transform(changed), changed, '변환은 멱등이어야 합니다.')
    # These test cases contain only hardcoded, benign assignments/returns.
    # Runtime execution of arbitrary user code is NOT part of this test helper.


class StringLiteralTriplets(unittest.TestCase):
    def test_basic(self):
        _check(self, 's = str()\n', string_style, "s = ''\n")

    def test_additional(self):
        _check(self, 'def f():\n    return str(None)\n', string_style,
               "def f():\n    return 'None'\n")

    def test_complex(self):
        original = '메모 = str(True)  # 주석 유지\r\nvalue = str(False)\r\n'
        expected = "메모 = 'True'  # 주석 유지\r\nvalue = 'False'\r\n"
        _check(self, original, string_style, expected)


class NumberLiteralTriplets(unittest.TestCase):
    def test_basic(self):
        _check(self, 'n = int()\n', number_style, 'n = 0\n')

    def test_additional(self):
        _check(self, 'n = int(True)  # 한글\n', number_style, 'n = 1  # 한글\n')

    def test_complex(self):
        _check(self, 'def f():\n    return int(False) + int(True)\n', number_style,
               'def f():\n    return 0 + 1\n')


class BooleanLiteralTriplets(unittest.TestCase):
    def test_basic(self):
        _check(self, 'flag = bool()\n', boolean_style, 'flag = False\n')

    def test_additional(self):
        _check(self, 'flag = bool(1)\n', boolean_style, 'flag = True\n')

    def test_complex(self):
        original = 'def f():\r\n    a = bool(None)\r\n    b = bool(0)\r\n    return a, b\r\n'
        expected = 'def f():\r\n    a = False\r\n    b = False\r\n    return a, b\r\n'
        _check(self, original, boolean_style, expected)


class Batch13SafetyTests(unittest.TestCase):
    def test_str_shadowed_by_assignment(self):
        source = 'x = str()\nstr = lambda: "overridden"\n'
        self.assertEqual(string_style(source), source)

    def test_arg_shadowed_in_function(self):
        source = 'def f(bool):\n    return bool()\n'
        self.assertEqual(boolean_style(source), source)

    def test_imports_and_dynamic_code_fail_closed(self):
        for source in ('import builtins\nx = int()\n',
                       'from math import sqrt\nx = int()\n',
                       'x = bool()\ny = globals()\n',
                       'x = str()\nexec("str = 42")\n',
                       'x = int()\n__import__("builtins")\n'):
            for transformer in (string_style, number_style, boolean_style):
                with self.subTest(source=source, transform=transformer.__name__):
                    self.assertEqual(transformer(source), source)

    def test_keyword_and_dynamic_arguments_not_rewritten(self):
        for code, transformer in (
            ('x = str(object())\n', string_style),
            ('x = int("12")\n', number_style),
            ('x = int(2.9)\n', number_style),
            ('x = bool([1])\n', boolean_style),
            ('x = bool(value)\n', boolean_style),
            ('x = str(123)\n', string_style),
            ('x = bool(2)\n', boolean_style),
            ('x = int(base=2)\n', number_style),
        ):
            with self.subTest(code=code):
                self.assertEqual(transformer(code), code)

    def test_interleaved_comment_inside_call_preserved(self):
        source = 'x = bool(  # important\n    1\n)\n'
        self.assertEqual(boolean_style(source), source)

    def test_nonmatching_builtin_is_untouched(self):
        self.assertEqual(number_style('n = str()\n'), 'n = str()\n')
        self.assertEqual(boolean_style('n = int()\n'), 'n = int()\n')

    def test_invalid_python_preserved(self):
        for transform in (string_style, number_style, boolean_style):
            self.assertEqual(transform('def bad(:\n'), 'def bad(:\n')

    def test_literal_results_preserve_value_and_type(self):
        # Compare canonical values for fixed, non-user-supplied expressions.
        cases = (
            ('str()', string_style), ('str(None)', string_style),
            ('str(True)', string_style), ('str(False)', string_style),
            ('int()', number_style), ('int(True)', number_style),
            ('int(False)', number_style), ('bool()', boolean_style),
            ('bool(0)', boolean_style), ('bool(1)', boolean_style),
            ('bool(None)', boolean_style),
        )
        for expression, transformer in cases:
            with self.subTest(expression=expression):
                compiled = transformer('v = ' + expression + '\n')
                before, after = {}, {}
                exec('v = ' + expression, before)
                exec(compiled, after)
                self.assertEqual(after['v'], before['v'])
                self.assertIs(type(after['v']), type(before['v']))


if __name__ == '__main__':
    unittest.main()
