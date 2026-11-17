"""R08: nested print helper conversion must not rewrite unused parameters."""
from __future__ import annotations

import ast
import importlib.util
import unittest

from tools.fix_batch36_4_r08_unused_parameter import MARKER, patch


_SAMPLE = '''import ast
import copy

def _change_wrapped_print_call(tree: ast.Module, stmt: ast.stmt, index: int):
    inner = stmt.value.args[0]
    signature = _module_function(tree, inner.func.id, index)
    if signature is None or len(inner.args) != len(signature):
        return None
    updated = copy.deepcopy(stmt)
    return [updated]
'''


class PatchTests(unittest.TestCase):
    def test_patch_is_idempotent(self):
        data, status = patch(_SAMPLE.encode())
        self.assertEqual(status, 'ready')
        self.assertIn(MARKER.encode(), data)
        self.assertEqual(patch(data), (data, 'already_applied'))

    def test_patch_refuses_unrecognised_source(self):
        with self.assertRaises(RuntimeError):
            patch(b'def wrong():\n    pass\n')

    def test_patch_refuses_duplicate_anchor(self):
        with self.assertRaises(RuntimeError):
            patch((_SAMPLE + _SAMPLE).encode())

    def test_patch_preserves_crlf(self):
        src = _SAMPLE.replace('\n', '\r\n').encode()
        data, status = patch(src)
        self.assertEqual(status, 'ready')
        self.assertNotIn(b'\n', data.replace(b'\r\n', b''))


try:
    _HAS_BACKEND = importlib.util.find_spec('app.services.style_diff_service') is not None
except ModuleNotFoundError:
    _HAS_BACKEND = False


@unittest.skipUnless(_HAS_BACKEND, 'full backend needed')
class ProductionIntegrationTests(unittest.TestCase):
    def run_transform(self, source):
        from app.services.improvement.safe_structural_patterns_service import (
            transform_positional_to_keyword_call,
        )
        return transform_positional_to_keyword_call(source)

    def test_r08_unchanged_through_full_style_service(self):
        from tools.audit_batch36_1 import evaluate_case
        from tools.batch36_1_cases import CASES
        sample = next(c for c in CASES if c.case_id == 'R08')
        row = evaluate_case(sample)
        self.assertFalse(row['changed'], row)
        self.assertEqual(row['resolved_tags'], [], row)
        self.assertFalse(row['errors'], row)

    def test_unused_argument_refused(self):
        src = 'def _f(x):\n    return 3\nprint(_f(3))\n'
        self.assertEqual(self.run_transform(src), src)

    def test_partially_unused_arguments_refused(self):
        src = 'def add(x, y):\n    return x + 3\nprint(add(2, 3))\n'
        self.assertEqual(self.run_transform(src), src)

    def test_used_arguments_still_convert(self):
        src = 'def add(x, y):\n    return x + y\nprint(add(2, 3))\n'
        changed = self.run_transform(src)
        self.assertIn('add(x=2, y=3)', changed)
        ast.parse(changed)

    def test_r43_still_verified(self):
        from tools.audit_batch36_1 import evaluate_case
        from tools.batch36_1_cases import CASES
        sample = next(c for c in CASES if c.case_id == 'R43')
        row = evaluate_case(sample)
        self.assertTrue(row['changed'], row)
        self.assertEqual(row['verification_status'], 'equivalent', row)

    def test_r45_composite_still_verified(self):
        from tools.audit_batch36_1 import evaluate_case
        from tools.batch36_1_cases import CASES
        sample = next(c for c in CASES if c.case_id == 'R45')
        row = evaluate_case(sample)
        self.assertEqual(row['verification_status'], 'equivalent', row)
        self.assertIn('리스트 컴프리헨션', row['resolved_tags'], row)

    def test_shadowed_builtin_print_still_refused(self):
        src = ('def print(x):\n    return x\n'
               'def add(a, b):\n    return a+b\nprint(add(2, 3))\n')
        self.assertEqual(self.run_transform(src), src)


if __name__ == '__main__':
    unittest.main()
