"""New positive 3-tier transformation regression cases (batch 6).

Every case must (1) actually change code, (2) remain parseable, and
(3) print the same output before and after transformation. The snippets
are trusted static fixtures and do not come from website input.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import unittest

from app.services.improvement.safe_syntax_patterns_service import (
    transform_def_to_lambda,
    transform_lambda_to_def,
    transform_if_to_match,
    transform_add_local_type_hints,
)
from app.services.improvement.safe_structural_patterns_service import (
    transform_suppress_to_try,
)


def _observed(source: str) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, '-I', '-c', source],
        text=True, capture_output=True, timeout=3, check=False,
    )
    return result.returncode, result.stdout, result.stderr


def assert_changed_equivalent(test: unittest.TestCase, code: str, transformer, expected: str):
    changed = transformer(code)
    test.assertNotEqual(changed, code, 'Transformer returned unchanged source')
    test.assertIn(expected, changed)
    test.assertNotEqual(ast.dump(ast.parse(code)), ast.dump(ast.parse(changed)),
                        'Only formatting changed, not the intended syntax')
    before = _observed(code)
    after = _observed(changed)
    test.assertEqual(before[0], 0, 'Original trusted fixture must run successfully')
    test.assertEqual(before, after)


class LambdaCreationTriplets(unittest.TestCase):
    def test_basic_one_parameter(self):
        code = 'def scale(x):\n    return x * 2\nprint(scale(4))\n'
        assert_changed_equivalent(self, code, transform_def_to_lambda, 'lambda x:')

    def test_additional_two_parameters(self):
        code = 'def combine(x, y):\n    return x * 10 + y\nprint(combine(3, 5))\n'
        assert_changed_equivalent(self, code, transform_def_to_lambda, 'lambda x, y:')

    def test_complex_nested_function(self):
        code = ('def outer():\n'
                '    def inner(value):\n'
                '        return value * 3\n'
                '    return inner(4)\n'
                'print(outer())\n')
        assert_changed_equivalent(self, code, transform_def_to_lambda, 'lambda value:')


class FunctionCreationTriplets(unittest.TestCase):
    def test_basic_one_parameter(self):
        code = 'scale = lambda x: x * 2\nprint(scale(4))\n'
        assert_changed_equivalent(self, code, transform_lambda_to_def, 'def scale(')

    def test_additional_two_parameters(self):
        code = 'combine = lambda x, y: x * 10 + y\nprint(combine(3, 5))\n'
        assert_changed_equivalent(self, code, transform_lambda_to_def, 'def combine(')

    def test_complex_nested_function(self):
        code = ('def outer():\n'
                '    inner = lambda value: value * 3\n'
                '    return inner(4)\n'
                'print(outer())\n')
        assert_changed_equivalent(self, code, transform_lambda_to_def, 'def inner(')


class PatternCreationTriplets(unittest.TestCase):
    def test_basic_integer_branches(self):
        code = ('value = 2\n'
                'if value == 1:\n    print("one")\n'
                'elif value == 2:\n    print("two")\n'
                'else:\n    print("other")\n')
        assert_changed_equivalent(self, code, transform_if_to_match, 'match value:')

    def test_additional_three_string_branches(self):
        code = ('value = "b"\n'
                'if value == "a":\n    print("A")\n'
                'elif value == "b":\n    print("B")\n'
                'elif value == "c":\n    print("C")\n'
                'else:\n    print("unknown")\n')
        assert_changed_equivalent(self, code, transform_if_to_match, 'match value:')

    def test_complex_method_body(self):
        code = ('class Formatter:\n'
                '    def render(self):\n'
                '        value = 3\n'
                '        if value == 1:\n            return "A"\n'
                '        elif value == 3:\n            return "C"\n'
                '        return "?"\n'
                'print(Formatter().render())\n')
        assert_changed_equivalent(self, code, transform_if_to_match, 'match value:')


class ExceptionCreationTriplets(unittest.TestCase):
    def test_basic_value_error(self):
        code = ('import contextlib\n'
                'with contextlib.suppress(ValueError):\n'
                '    value = int("bad")\n'
                'print("done")\n')
        assert_changed_equivalent(self, code, transform_suppress_to_try, 'except ValueError:')

    def test_additional_key_error(self):
        code = ('import contextlib\n'
                'with contextlib.suppress(KeyError):\n'
                '    value = {"a": 1}["missing"]\n'
                'print("done")\n')
        assert_changed_equivalent(self, code, transform_suppress_to_try, 'except KeyError:')

    def test_complex_two_context_managers(self):
        code = ('import contextlib\n'
                'with contextlib.suppress(ZeroDivisionError):\n'
                '    x = 1 / 0\n'
                'with contextlib.suppress(KeyError):\n'
                '    y = {"a": 4}["a"]\n'
                'print(y)\n')
        assert_changed_equivalent(self, code, transform_suppress_to_try, 'except ZeroDivisionError:')


class TypeHintCreationTriplets(unittest.TestCase):
    def test_basic_integer_assignment(self):
        code = ('def f():\n    x = 2\n    return x * 2\nprint(f())\n')
        assert_changed_equivalent(self, code, transform_add_local_type_hints, 'x: int = 2')

    def test_additional_string_assignment(self):
        code = ('def f():\n    text = "hi"\n    return text.upper()\nprint(f())\n')
        assert_changed_equivalent(self, code, transform_add_local_type_hints, 'text: str =')

    def test_complex_multiple_types_inside_function(self):
        code = ('def calculate():\n'
                '    amount = 7\n'
                '    active = True\n'
                '    label = "item"\n'
                '    return label, amount, active\n'
                'print(calculate())\n')
        assert_changed_equivalent(self, code, transform_add_local_type_hints, 'amount: int =')


if __name__ == '__main__':
    unittest.main()
