"""Regression tests for Batch36-3's shadowed-print hotfix."""
from __future__ import annotations

import ast
import unittest

from tools.fix_batch36_3_shadowed_print import BEFORE, AFTER, REQUIRES, MARKER, patch


class PatchContractTests(unittest.TestCase):
    @staticmethod
    def fixture() -> bytes:
        source = '''import ast
# CAPSTONE_BATCH36_3_NESTED_KEYWORD_V1

def f(tree, stmt, direction, i):
    replacements = None
    if True:
        if True:
            if True:
                if True:
''' + BEFORE + '\n    return replacements\n'
        ast.parse(source)
        return source.encode('utf-8')

    def test_rewrites_anchor_once(self):
        result, status = patch(self.fixture())
        self.assertEqual(status, 'ready')
        self.assertIn(MARKER.encode('utf-8'), result)
        self.assertNotIn(BEFORE.encode('utf-8'), result)
        ast.parse(result)

    def test_idempotent(self):
        result, _ = patch(self.fixture())
        repeated, status = patch(result)
        self.assertEqual(status, 'already_applied')
        self.assertEqual(result, repeated)

    def test_fails_closed_without_original_batch36_3(self):
        with self.assertRaises(RuntimeError):
            patch(self.fixture().replace(REQUIRES.encode('utf-8'), b'not_installed'))

    def test_fails_closed_when_anchor_is_absent(self):
        with self.assertRaises(RuntimeError):
            patch(b'# ' + REQUIRES.encode('utf-8') + b'\n')

    def test_keeps_crlf(self):
        source = self.fixture().replace(b'\n', b'\r\n')
        result, status = patch(source)
        self.assertEqual(status, 'ready')
        self.assertNotIn(b'\n', result.replace(b'\r\n', b''))


try:
    from app.services.improvement.safe_structural_patterns_service import (
        transform_positional_to_keyword_call,
        transform_keyword_to_positional_call,
    )
except ImportError:
    _BACKEND_AVAILABLE = False
else:
    _BACKEND_AVAILABLE = True


@unittest.skipUnless(_BACKEND_AVAILABLE, 'Production backend not installed in standalone environment')
class ProductionRegressionTests(unittest.TestCase):
    def test_shadowed_print_inside_nested_call_is_not_rewritten(self):
        code = ('def print(x):\n    return x\n'
                'def combine(a, b):\n    return a + b\n'
                'print(combine(2, 3))\n')
        self.assertEqual(transform_positional_to_keyword_call(code), code)

    def test_direct_shadowed_print_not_rewritten(self):
        code = 'def print(x):\n    return x\nprint(3)\n'
        self.assertEqual(transform_positional_to_keyword_call(code), code)

    def test_builtin_print_nested_call_still_rewritten(self):
        code = 'def combine(a, b):\n    return a + b\nprint(combine(2, 3))\n'
        after = transform_positional_to_keyword_call(code)
        self.assertIn('combine(a=2, b=3)', after)
        self.assertEqual(ast.dump(ast.parse(code).body[0].body[0].value),
                         ast.dump(ast.parse(after).body[0].body[0].value))

    def test_other_regular_function_remains_supported(self):
        code = 'def combine(a, b):\n    return a + b\ncombine(2, 3)\n'
        after = transform_positional_to_keyword_call(code)
        self.assertIn('combine(a=2, b=3)', after)

    def test_reverse_keyword_to_positional_not_changed(self):
        code = 'def combine(a, b):\n    return a + b\ncombine(a=2, b=3)\n'
        after = transform_keyword_to_positional_call(code)
        self.assertIn('combine(2, 3)', after)


if __name__ == '__main__':
    unittest.main()
