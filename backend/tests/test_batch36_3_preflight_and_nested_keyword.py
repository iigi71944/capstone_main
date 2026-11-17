"""Batch36-3: shape-screening safety, patch contracts, integration fixtures."""
from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

from app.services.style_action_preflight_service import (
    SCREENED_ACTIONS, screen_action_candidate,
)
from tools.apply_batch36_3 import PATCHES, _patch
from tools.audit_batch36_3 import make_report, validate_baseline
try:
    from app.services.style_diff_service import analyze_code_style as _backend_marker
except ImportError:
    _BACKEND_AVAILABLE = False
else:
    _BACKEND_AVAILABLE = True


class ShapeScreeningTests(unittest.TestCase):
    def test_screened_set_is_exactly_three(self):
        self.assertEqual(len(SCREENED_ACTIONS), 3)

    def test_unknown_action_is_untouched(self):
        self.assertIsNone(screen_action_candidate('create_safe_comprehension_collection', 'x = 1\n'))

    def test_invalid_python_delegates_to_original_verifier(self):
        self.assertIsNone(screen_action_candidate('create_safe_operator_call', 'def (\n'))

    def test_operator_without_import_is_screened(self):
        ans = screen_action_candidate('create_safe_operator_call', 'x = 2 + 3\n')
        self.assertEqual(ans['reason_code'], 'missing_required_ast_shape')

    def test_operator_import_after_assignment_is_screened(self):
        self.assertIsNotNone(screen_action_candidate('create_safe_operator_call', 'x = 2 + 3\nimport operator\n'))

    def test_operator_with_import_before_simple_assignment_is_preserved(self):
        self.assertIsNone(screen_action_candidate('create_safe_operator_call', 'import operator\nx = 2 + 3\n'))

    def test_operator_with_print_expression_is_screened(self):
        self.assertIsNotNone(screen_action_candidate('create_safe_operator_call', 'import operator\nprint(2 + 3)\n'))

    def test_getattr_assignment_is_preserved(self):
        self.assertIsNone(screen_action_candidate('create_safe_direct_attribute', "out = getattr(obj, 'x')\n"))

    def test_getattr_expression_is_preserved(self):
        self.assertIsNone(screen_action_candidate('create_safe_direct_attribute', "getattr(obj, 'x')\n"))

    def test_getattr_nested_in_print_is_screened(self):
        self.assertIsNotNone(screen_action_candidate('create_safe_direct_attribute', "print(getattr(obj, 'x'))\n"))

    def test_getattr_three_argument_variant_is_screened(self):
        self.assertIsNotNone(screen_action_candidate('create_safe_direct_attribute', "out = getattr(obj, 'x', 0)\n"))

    def test_keyword_direct_function_call_preserved(self):
        code = 'def f(x):\n    return x\nf(3)\n'
        self.assertIsNone(screen_action_candidate('create_safe_keyword_call', code))

    def test_keyword_nested_print_literal_preserved(self):
        code = 'def f(x):\n    return x\nprint(f(3))\n'
        self.assertIsNone(screen_action_candidate('create_safe_keyword_call', code))

    def test_keyword_nested_print_nonliteral_screened(self):
        code = 'def f(x):\n    return x\nv=3\nprint(f(v))\n'
        self.assertIsNotNone(screen_action_candidate('create_safe_keyword_call', code))

    def test_keyword_undefined_function_screened(self):
        self.assertIsNotNone(screen_action_candidate('create_safe_keyword_call', 'print(f(2))\n'))

    def test_keyword_function_after_call_screened(self):
        code = 'print(f(2))\ndef f(x):\n    return x\n'
        self.assertIsNotNone(screen_action_candidate('create_safe_keyword_call', code))

    def test_keyword_ambiguous_signature_screened(self):
        code = 'def f(a, b):\n    return a+b\nprint(f(1))\n'
        self.assertIsNotNone(screen_action_candidate('create_safe_keyword_call', code))

    def test_screening_is_deterministic(self):
        code = 'def f(a):\n    return a\nprint(f(2))\n'
        a = screen_action_candidate('create_safe_keyword_call', code)
        b = screen_action_candidate('create_safe_keyword_call', code)
        self.assertEqual(a, b)


class InstallerTests(unittest.TestCase):
    def _fixture(self, name):
        lines = []
        for old, _ in PATCHES[name]:
            if name.endswith('style_apply_service.py'):
                # The repeated fragments are embedded in a syntactically valid
                # skeleton matching their actual enclosing function.
                return '''from app.services.style_action_diagnostic_service import build_transform_diagnostics

def _apply_style_action(*, code, action_item,
    applied_rules: list[str],
    warnings: list[str],
) -> tuple[str, dict]:
    action = action_item.get("action")
    tag_name = "x"
    result = {}
    transform_func = lambda code: code
    before = code
    try:
        after = transform_func(code)
    except Exception:
        return code, result
    return after, result

def apply_coding_style():
    metric_info = {}
    action_item = {}
    transformed_code = ""
    applied_rules = []
    warnings = []
    transformed_code, action_result = _apply_style_action(
            code=transformed_code,
            action_item=action_item,
            applied_rules=applied_rules,
            warnings=warnings,
        )
'''
            if name.endswith('style_action_outcome_service.py'):
                return '''_STATUS = {
    "no_safe_pattern": ("skipped", "적용할 안전한 코드 패턴 없음"),
}
'''
            if name.endswith('style_action_diagnostic_service.py'):
                return '''_STATUS_REASON = {
    "no_safe_pattern": ("no_safe_pattern", "대상 코드에서 변환기의 안전 조건을 만족하는 패턴을 찾지 못했습니다."),
}

def _attempt_result(raw, verification=None):
    tag = raw.get('tag')
    action = raw.get('action')
    status = raw.get('status')
    reason_code, reason = _STATUS_REASON.get(status, ('unknown', 'unknown'))
    result = {
        "tag": tag, "action": action, "status": status,
        "reason_code": reason_code, "reason": reason,
    }
    return result
'''
            return '''import ast

def _convert_attribute(tree: ast.Module, stmt: ast.stmt, direction: str) -> list[ast.stmt] | None:
    return None

def _rewrite(code, direction):
    replacements = None
    i = 0
    stmt = ast.parse('print(2)').body[0]
    tree = ast.parse(code)
    if True:
        if True:
            if True:
                if True:
                    if True:
                        if signature is not None:
                            replacements = _change_call(stmt, signature, direction)
    return code
'''
        return '\n'.join(lines)

    def test_each_patch_missing_anchor_fails_closed(self):
        for filename in PATCHES:
            with self.subTest(filename=filename):
                with self.assertRaises(RuntimeError):
                    _patch(filename, b'from nowhere import nothing\n')

    def test_each_patch_idempotence(self):
        for filename in PATCHES:
            with self.subTest(filename=filename):
                base = self._fixture(filename).encode('utf-8')
                patched, status = _patch(filename, base)
                self.assertEqual(status, 'ready')
                ast.parse(patched)
                repeated, status2 = _patch(filename, patched)
                self.assertEqual(status2, 'already_applied')
                self.assertEqual(repeated, patched)

    def test_preserve_crlf(self):
        filename = 'app/services/style_action_diagnostic_service.py'
        src = self._fixture(filename).replace('\n', '\r\n').encode('utf-8')
        patched, status = _patch(filename, src)
        self.assertEqual(status, 'ready')
        self.assertIn(b'\r\n', patched)
        self.assertNotIn(b'\n', patched.replace(b'\r\n', b''))


@unittest.skipUnless(_BACKEND_AVAILABLE, "Full production backend unavailable in standalone smoke")
class FullBackendTests(unittest.TestCase):
    def test_nested_print_keyword_transform(self):
        from app.services.improvement.safe_structural_patterns_service import transform_positional_to_keyword_call
        code = 'def combine(a, b):\n    return a + b\nprint(combine(2, 3))\n'
        after = transform_positional_to_keyword_call(code)
        self.assertNotEqual(code, after)
        self.assertIn('combine(a=2, b=3)', after)
        self.assertEqual(ast.dump(ast.parse(code).body[0].body[0].value),
                         ast.dump(ast.parse(after).body[0].body[0].value))

    def test_nested_keyword_bails_on_dynamic_args(self):
        from app.services.improvement.safe_structural_patterns_service import transform_positional_to_keyword_call
        code = 'def combine(a, b):\n    return a + b\nprint(combine(1 + 2, 3))\n'
        self.assertEqual(transform_positional_to_keyword_call(code), code)

    def test_nested_keyword_bails_on_shadowed_print(self):
        from app.services.improvement.safe_structural_patterns_service import transform_positional_to_keyword_call
        code = 'def print(x):\n    return x\ndef combine(a, b):\n    return a + b\nprint(combine(2, 3))\n'
        self.assertEqual(transform_positional_to_keyword_call(code), code)

    def test_nested_keyword_bails_on_nonclosed_module(self):
        from app.services.improvement.safe_structural_patterns_service import transform_positional_to_keyword_call
        code = 'def combine(a, b):\n    return a + b\nx = 2\nprint(combine(2, 3))\n'
        self.assertEqual(transform_positional_to_keyword_call(code), code)

    def test_nested_keyword_preserves_comments(self):
        from app.services.improvement.safe_structural_patterns_service import transform_positional_to_keyword_call
        code = 'def combine(a, b):\n    return a + b\nprint(combine(2, 3)) # do not change\n'
        self.assertEqual(transform_positional_to_keyword_call(code), code)

    def test_nested_keyword_bails_on_mutable_scope(self):
        from app.services.improvement.safe_structural_patterns_service import transform_positional_to_keyword_call
        code = 'def combine(a, b):\n    return a+b\ncombine = lambda x, y: x+y\nprint(combine(2, 3))\n'
        self.assertEqual(transform_positional_to_keyword_call(code), code)

    def test_target_R43_now_changes_with_runtime_verification(self):
        from tools.audit_batch36_1 import evaluate_case
        from tools.batch36_1_cases import CASES
        row = evaluate_case(next(case for case in CASES if case.case_id == 'R43'))
        self.assertTrue(row['changed'], row)
        self.assertEqual(row['verification_status'], 'equivalent', row)

    def test_strict_async_rollbacks_unchanged(self):
        from tools.audit_batch36_1 import evaluate_case
        from tools.batch36_1_cases import CASES
        for case in CASES:
            if case.case_id in ('R04', 'R05', 'R06'):
                with self.subTest(case=case.case_id):
                    row = evaluate_case(case, strict_runtime_validation=True)
                    self.assertFalse(row['changed'], row)
                    self.assertEqual(row['verification_status'], 'not_verified', row)

    def test_preflight_diagnostic_metadata(self):
        from app.services.style_action_diagnostic_service import build_transform_diagnostics
        plan = {'omitted_actions': [], 'compare_only': [], 'not_selected_tags': []}
        attempted = [{'tag': '속성 접근', 'action': 'create_safe_direct_attribute',
                      'status': 'skipped_shape_preflight',
                      'preflight_reason_code': 'missing_required_ast_shape',
                      'preflight_reason': 'necessary shape missing'}]
        row = build_transform_diagnostics(plan, attempted)['attempted_actions'][0]
        self.assertEqual(row['reason_code'], 'missing_required_ast_shape')
        self.assertEqual(row['reason'], 'necessary shape missing')


if __name__ == '__main__':
    unittest.main()
