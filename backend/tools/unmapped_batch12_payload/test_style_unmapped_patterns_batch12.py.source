"""Batch 12: nine positive representative cases plus conservative rejection tests."""
from __future__ import annotations

import ast
import unittest

from app.services.improvement.safe_unmapped_patterns_batch12_service import (
    transform_to_safe_guard_continue_style as to_continue,
    transform_to_safe_literal_identity_style as to_identity,
)
from app.services.improvement.safe_remaining_patterns_service import (
    transform_operator_call_to_arithmetic as to_arithmetic,
)


def _run(source: str, function: str, args: tuple):
    namespace = {'__name__': '__batch12_test__'}
    exec(compile(source, '<batch12-test>', 'exec'), namespace, namespace)
    return namespace[function](*args)


class ContinueTriplets(unittest.TestCase):
    def test_basic(self):
        code = '''def selected(values):
    out = []
    for n in values:
        if n < 0:
            pass
        else:
            out.append(n)
    return out
'''
        result = to_continue(code)
        self.assertNotEqual(result, code)
        self.assertIn('continue', result)
        ast.parse(result)
        for values in ([1, -1, 2], [], [-4, -2]):
            self.assertEqual(_run(code, 'selected', (values,)),
                             _run(result, 'selected', (values,)))

    def test_additional(self):
        code = '''def selected(values):
    answer = 0
    for n in values:
        if n % 2 == 0:
            pass
        else:
            answer += n
    return answer
'''
        result = to_continue(code)
        self.assertIn('continue', result)
        for values in ([], [1, 2, 3, 4], [-3, -2, 3]):
            self.assertEqual(_run(code, 'selected', (values,)),
                             _run(result, 'selected', (values,)))

    def test_complex(self):
        code = '''def selected(values):
    last = "없음"
    for n in values:
        if n == "skip":
            pass
        else:
            last = n
    else:
        last += "!"
    return last
'''
        result = to_continue(code)
        self.assertIn('continue', result)
        self.assertIn('else:', result)  # original for-else preserved
        for values in ([], ['skip'], ['ok', 'skip', 'hi']):
            self.assertEqual(_run(code, 'selected', (values,)),
                             _run(result, 'selected', (values,)))


class IdentityTriplets(unittest.TestCase):
    def test_basic(self):
        code = '''def check():
    value = None
    if value == None:
        return 1
    return 0
'''
        result = to_identity(code)
        self.assertIn('value is None', result)
        self.assertEqual(_run(code, 'check', ()), _run(result, 'check', ()))

    def test_additional(self):
        code = '''def check():
    value = -2
    if value != None:
        return value
    return 0
'''
        result = to_identity(code)
        self.assertIn('value is not None', result)
        self.assertEqual(_run(code, 'check', ()), _run(result, 'check', ()))

    def test_complex(self):
        code = '''def check():
    result = []
    for value in ("a", "b"):
        label = "확인"
        if None == label:
            result.append("none")
        else:
            result.append(value)
    return result
'''
        result = to_identity(code)
        self.assertIn('None is label', result)
        self.assertEqual(_run(code, 'check', ()), _run(result, 'check', ()))


class ArithmeticTriplets(unittest.TestCase):
    def test_basic(self):
        code = 'import operator\nresult = operator.add(3, 4)\n'
        result = to_arithmetic(code)
        self.assertNotEqual(code, result)
        self.assertIn('3 + 4', result)
        self.assertEqual(_value(code), _value(result))

    def test_additional(self):
        code = 'import operator\nresult = operator.sub(8, 5)\n'
        result = to_arithmetic(code)
        self.assertNotEqual(code, result)
        self.assertIn('8 - 5', result)
        self.assertEqual(_value(code), _value(result))

    def test_complex(self):
        code = 'import operator\na = 6\nb = 4\nresult = operator.mul(a, b)\n'
        result = to_arithmetic(code)
        self.assertNotEqual(code, result)
        self.assertIn('*', result)
        self.assertEqual(_value(code), _value(result))


def _value(source: str):
    namespace = {'__name__': '__batch12_test__'}
    exec(compile(source, '<batch12-test>', 'exec'), namespace, namespace)
    return namespace['result']


class Batch12SafetyTests(unittest.TestCase):
    def test_continue_must_be_last(self):
        code = '''for n in [1, 2]:
    if n < 0:
        pass
    else:
        print(n)
    print("always")
'''
        self.assertEqual(to_continue(code), code)

    def test_continue_comments_inside_block_are_preserved(self):
        code = '''for n in [1, 2]:
    if n < 0:
        pass
    else:
        # a comment about the following call
        print(n)
'''
        self.assertEqual(to_continue(code), code)

    def test_continue_multiline_else_unchanged(self):
        code = '''for n in [1]:
    if n < 0:
        pass
    else:
        print(
            n
        )
'''
        self.assertEqual(to_continue(code), code)

    def test_identity_custom_equality_never_rewritten(self):
        code = '''class Weird:
    def __eq__(self, rhs):
        return rhs is None
value = Weird()
if value == None:
    print("special")
'''
        self.assertEqual(to_identity(code), code)

    def test_identity_intervening_rebind_never_rewritten(self):
        code = '''value = None
value = compute()
if value == None:
    print(1)
'''
        self.assertEqual(to_identity(code), code)

    def test_identity_no_preceding_literal_never_rewritten(self):
        code = '''def check(value):
    if value == None:
        return True
    return False
'''
        self.assertEqual(to_identity(code), code)

    def test_comments_crlf_and_unicode_preserved(self):
        code = ('# 한글 주석\r\nvalue = "한글"\r\n'
                'if value == None:  # keep me\r\n    print(1)\r\n')
        result = to_identity(code)
        self.assertIn('value is None', result)
        self.assertIn('# 한글 주석\r\n', result)
        self.assertIn('  # keep me\r\n', result)
        self.assertNotIn('\n', result.replace('\r\n', ''))

    def test_continue_crlf_round_trip(self):
        code = ('for n in [1, 2]:\r\n'
                '    if n == 1:\r\n'
                '        pass\r\n'
                '    else:\r\n'
                '        print(n)\r\n')
        result = to_continue(code)
        self.assertIn('continue', result)
        self.assertNotIn('\n', result.replace('\r\n', ''))

    def test_repeat_is_idempotent(self):
        a = 'value = 1\nif value != None:\n    print(value)\n'
        once = to_identity(a)
        self.assertEqual(to_identity(once), once)
        b = 'for n in [1]:\n    if n < 0:\n        pass\n    else:\n        print(n)\n'
        twice = to_continue(b)
        self.assertEqual(to_continue(twice), twice)


if __name__ == '__main__':
    unittest.main()
