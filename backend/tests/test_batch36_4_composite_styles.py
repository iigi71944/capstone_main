"""Meaningful Batch36-4 tests: closed helper patterns and style-engine safety."""
from __future__ import annotations

import ast
import importlib.util
import unittest

from app.services.improvement.safe_composite_list_service import (
    _rewrite_closed_pure_helper_loop,
    transform_safe_composite_list_comprehension,
)
from tools.apply_batch36_4 import patch, OLD_IMPORT, OLD_MAP, MARKER
from tools.audit_batch36_4 import validate_baseline

DEF = '''nums = [1, 2, 3]
def inc(x):
    return x + 1
out = []
for x in nums:
    out.append(inc(x))
print(out)
'''
LAMBDA = '''nums = [1, 2, 3]
inc = lambda x: x + 1
out = []
for x in nums:
    out.append(inc(x))
print(out)
'''


class ClosedCompositionTests(unittest.TestCase):
    def test_pure_def_helper_collapses(self):
        after = _rewrite_closed_pure_helper_loop(DEF)
        self.assertNotEqual(after, DEF)
        self.assertIn('out = [inc(x) for x in nums]', after)
        ast.parse(after)

    def test_pure_lambda_helper_collapses(self):
        after = _rewrite_closed_pure_helper_loop(LAMBDA)
        self.assertNotEqual(after, LAMBDA)
        self.assertIn('out = [inc(x) for x in nums]', after)
        ast.parse(after)

    def test_local_simple_arithmetic_is_the_only_supported_helper(self):
        for snippet in ('return x * 2', 'return x - 1', 'return x + 3'):
            with self.subTest(snippet=snippet):
                code = DEF.replace('return x + 1', snippet)
                self.assertIn('out = [inc(x) for x in nums]',
                              _rewrite_closed_pure_helper_loop(code))
        for snippet in ('return x + x', 'return x / 2', 'return abs(x)',
                        'return x + globals()["k"]'):
            with self.subTest(snippet=snippet):
                code = DEF.replace('return x + 1', snippet)
                self.assertEqual(_rewrite_closed_pure_helper_loop(code), code)

    def test_preserve_print_and_other_statements(self):
        changed = _rewrite_closed_pure_helper_loop(DEF)
        self.assertTrue(changed.startswith('nums = [1, 2, 3]\ndef inc(x):'))
        self.assertTrue(changed.endswith('print(out)\n'))

    def test_reject_print_shadowing(self):
        bad = DEF.replace('def inc(x):', 'def print(x):')
        self.assertEqual(_rewrite_closed_pure_helper_loop(bad), bad)
        bad = DEF.replace('nums = [1, 2, 3]', 'print = [1, 2, 3]')
        self.assertEqual(_rewrite_closed_pure_helper_loop(bad), bad)

    def test_reject_rebinding_or_alias(self):
        bad = DEF.replace('out = []', 'inc = alias\nout = []')
        self.assertEqual(_rewrite_closed_pure_helper_loop(bad), bad)
        bad2 = DEF.replace('out.append(inc(x))', 'out.append(other(x))')
        self.assertEqual(_rewrite_closed_pure_helper_loop(bad2), bad2)

    def test_reject_indirect_or_effectful_helpers(self):
        bad = DEF.replace('return x + 1', 'return print(x)')
        self.assertEqual(_rewrite_closed_pure_helper_loop(bad), bad)
        bad = DEF.replace('    return x + 1', '    print(x)\n    return x + 1')
        self.assertEqual(_rewrite_closed_pure_helper_loop(bad), bad)

    def test_reject_mutable_or_unknown_iteration_input(self):
        for value in ('range(3)', 'unknown', '[1, func(), 3]', '[]'):
            with self.subTest(value=value):
                bad = DEF.replace('nums = [1, 2, 3]', 'nums = ' + value)
                self.assertEqual(_rewrite_closed_pure_helper_loop(bad), bad)

    def test_reject_live_loop_variable_after_loop(self):
        bad = DEF.replace('print(out)', 'print(x)')
        self.assertEqual(_rewrite_closed_pure_helper_loop(bad), bad)
        bad = DEF + 'print(x)\n'
        self.assertEqual(_rewrite_closed_pure_helper_loop(bad), bad)

    def test_comment_and_semicolon_excluded(self):
        bad = DEF.replace('out = []', 'out = []  # preserve this explanation')
        self.assertEqual(_rewrite_closed_pure_helper_loop(bad), bad)
        bad = DEF.replace('out.append(inc(x))', 'out.append(inc(x)); print("loop")')
        self.assertEqual(_rewrite_closed_pure_helper_loop(bad), bad)

    def test_invalid_and_non_string_input_preserved(self):
        source = 'def (\n'
        self.assertEqual(_rewrite_closed_pure_helper_loop(source), source)
        self.assertEqual(_rewrite_closed_pure_helper_loop(''), '')
        self.assertIsNone(_rewrite_closed_pure_helper_loop(None))

    def test_non_composite_code_not_rewritten(self):
        source = 'nums = [1, 2]\nout=[]\nfor x in nums:\n    out.append(x + 1)\nprint(out)\n'
        self.assertEqual(_rewrite_closed_pure_helper_loop(source), source)

    def test_crlf_preserved_in_composite(self):
        code = LAMBDA.replace('\n', '\r\n')
        after = _rewrite_closed_pure_helper_loop(code)
        self.assertIn('out = [inc(x) for x in nums]\r\n', after)
        self.assertNotIn('\n', after.replace('\r\n', ''))


class InstallationContractTests(unittest.TestCase):
    @staticmethod
    def stub():
        return ("import ast\n" + OLD_IMPORT +
                "def _get_transform_function(action):\n"
                "    action_map = {\n        " + OLD_MAP + "\n    }\n"
                "    return action_map.get(action)\n").encode('utf-8')

    def test_installer_idempotence(self):
        first, status = patch(self.stub())
        self.assertEqual(status, 'ready')
        self.assertIn(MARKER.encode(), first)
        second, status = patch(first)
        self.assertEqual(status, 'already_applied')
        self.assertEqual(first, second)

    def test_installer_refuses_wrong_version(self):
        with self.assertRaises(RuntimeError):
            patch(b'import ast\n')
        with self.assertRaises(RuntimeError):
            patch(("# " + MARKER + "\n" + OLD_IMPORT + OLD_MAP).encode())

    def test_installer_preserves_crlf(self):
        old = self.stub().replace(b'\n', b'\r\n')
        new, status = patch(old)
        self.assertEqual(status, 'ready')
        self.assertNotIn(b'\n', new.replace(b'\r\n', b''))

    def test_baseline_rejects_invalid_audit(self):
        with self.assertRaises(ValueError):
            validate_baseline({'report_version': 1, 'current': {'changed': 37}})
        baseline = {'report_version': 1, 'current': {
            'changed': 37, 'verified_changes': 34,
            'no_safe_pattern': 55, 'preflight_skipped': 21,
        }, 'contract': {'action_ledger_consistent': True}}
        self.assertEqual(validate_baseline(baseline)['changed'], 37)


@unittest.skipUnless(
    importlib.util.find_spec('app.services.style_diff_service') is not None,
    'Full backend services are required for integration checks',
)
class ProductionIntegrationTests(unittest.TestCase):
    def test_wrapper_keeps_existing_general_list_conversion(self):
        source = 'xs = [1, 2]\nout = []\nfor x in xs:\n    out.append(x + 1)\nprint(out)\n'
        changed = transform_safe_composite_list_comprehension(source)
        self.assertIn('for x in xs', source)
        self.assertIn('out = [x + 1 for x in xs]', changed)

    def test_wrapper_transforms_pure_helper(self):
        self.assertIn('out = [inc(x) for x in nums]',
                      transform_safe_composite_list_comprehension(DEF))

    def test_runtime_equivalence_observed_for_def_and_lambda(self):
        from app.services.execution_validation_service import verify_execution_equivalence
        for source in (DEF, LAMBDA):
            with self.subTest(kind='lambda' if source == LAMBDA else 'def'):
                converted = transform_safe_composite_list_comprehension(source)
                outcome = verify_execution_equivalence(source, converted)
                self.assertEqual(outcome['status'], 'equivalent', outcome)

    def test_existing_50_case_R45_composite_applies(self):
        from tools.audit_batch36_1 import evaluate_case
        from tools.batch36_1_cases import CASES
        sample = next(case for case in CASES if case.case_id == 'R45')
        outcome = evaluate_case(sample)
        self.assertTrue(outcome['changed'], outcome)
        self.assertEqual(outcome['verification_status'], 'equivalent', outcome)
        self.assertTrue({'lambda식', '리스트 컴프리헨션'} <= set(outcome['resolved_tags']), outcome)
        self.assertEqual(outcome['final_missing_tags'], [], outcome)

    def test_negative_shape_R08_remains_unchanged(self):
        from tools.audit_batch36_1 import evaluate_case
        from tools.batch36_1_cases import CASES
        outcome = evaluate_case(next(c for c in CASES if c.case_id == 'R08'))
        self.assertFalse(outcome['changed'], outcome)


if __name__ == '__main__':
    unittest.main()
