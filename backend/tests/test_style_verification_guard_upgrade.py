"""Regression tests for runtime-verifier failure handling.

All verifiers and transformers here are mocks; user code is never executed.
"""

import unittest
from unittest.mock import patch

from app.services import style_apply_service as style_service

ORIGINAL = "value = 1\n"
CHANGED = "value = 2\n"
ACTION = {"tag": "검증 테스트", "action": "create_test_action", "reason": "테스트"}


def run_case(verdict=None, *, error=None, strict=False, changed=True,
             cases=None, existing_plan=True):
    plan = {"actions": [ACTION] if existing_plan else [], "compare_only": []}
    new_source = CHANGED if changed else ORIGINAL
    with patch.object(style_service, "compare_style_with_target_code", return_value={}), \
         patch.object(style_service, "build_transform_plan", return_value=plan), \
         patch.object(style_service, "compare_after_transform", return_value={
             "missing_syntax_tags": [], "missing_concept_tags": []}), \
         patch.object(style_service, "_get_transform_function", return_value=lambda _code: new_source), \
         patch.object(style_service, "verify_execution_equivalence") as verifier:
        if error:
            verifier.side_effect = error
        else:
            verifier.return_value = verdict
        result = style_service.apply_coding_style(
            ORIGINAL, {"syntax_tags": [], "concept_tags": []},
            function_cases=cases, strict_runtime_validation=strict,
        )
        return result, verifier.call_count


class RuntimeVerificationGuardTests(unittest.TestCase):
    EQUIV = {"status": "equivalent", "equivalent": True, "message": "같음"}
    DIFFERENT = {"status": "different", "equivalent": False, "message": "다름"}
    UNVERIFIED = {"status": "not_verified", "equivalent": None, "message": "제한"}

    def test_verified_transform_kept(self):
        out, calls = run_case(self.EQUIV)
        self.assertEqual(out[0], CHANGED)
        self.assertEqual(calls, 1)

    def test_verified_transform_keeps_applied_rule(self):
        out, _ = run_case(self.EQUIV)
        self.assertEqual(len(out[2]), 1)

    def test_difference_rolls_back(self):
        out, _ = run_case(self.DIFFERENT)
        self.assertEqual(out[0], ORIGINAL)
        self.assertEqual(out[2], [])
        self.assertIn('취소', ''.join(out[3]))

    def test_difference_summary(self):
        out, _ = run_case(self.DIFFERENT)
        self.assertIn('원본 코드', out[1])

    def test_verifier_exception_rolls_back_without_crash(self):
        out, _ = run_case(error=RuntimeError('demo'))
        self.assertEqual(out[0], ORIGINAL)
        self.assertEqual(out[5]['status'], 'not_verified')
        self.assertIn('RuntimeError', out[5]['message'])

    def test_timeout_exception_rolls_back(self):
        out, _ = run_case(error=TimeoutError())
        self.assertEqual(out[0], ORIGINAL)
        self.assertTrue(out[3])

    def test_none_result_rolls_back(self):
        out, _ = run_case(None)
        self.assertEqual(out[0], ORIGINAL)

    def test_string_result_rolls_back(self):
        out, _ = run_case('success')
        self.assertEqual(out[0], ORIGINAL)

    def test_unknown_status_rolls_back(self):
        out, _ = run_case({"status":"ok", "equivalent":True})
        self.assertEqual(out[0], ORIGINAL)

    def test_unhashable_status_rolls_back(self):
        out, _ = run_case({"status": [], "equivalent": True})
        self.assertEqual(out[0], ORIGINAL)

    def test_missing_status_rolls_back(self):
        out, _ = run_case({"equivalent":True})
        self.assertEqual(out[0], ORIGINAL)

    def test_equivalent_false_rolls_back(self):
        out, _ = run_case({"status":"equivalent", "equivalent":False})
        self.assertEqual(out[0], ORIGINAL)

    def test_equivalent_none_rolls_back(self):
        out, _ = run_case({"status":"equivalent", "equivalent":None})
        self.assertEqual(out[0], ORIGINAL)

    def test_equivalent_non_boolean_rolls_back(self):
        out, _ = run_case({"status":"equivalent", "equivalent":1})
        self.assertEqual(out[0], ORIGINAL)

    def test_not_verified_legacy_mode_preserves_result_with_warning(self):
        out, _ = run_case(self.UNVERIFIED)
        self.assertEqual(out[0], CHANGED)
        self.assertIn('검증', ''.join(out[3]))

    def test_not_verified_strict_rolls_back(self):
        out, _ = run_case(self.UNVERIFIED, strict=True)
        self.assertEqual(out[0], ORIGINAL)
        self.assertEqual(out[2], [])
        self.assertIn('원본', out[1])

    def test_strict_mode_allows_equivalent(self):
        out, _ = run_case(self.EQUIV, strict=True)
        self.assertEqual(out[0], CHANGED)

    def test_unchanged_code_does_not_call_verifier(self):
        out, count = run_case(self.EQUIV, changed=False)
        self.assertEqual(out[0], ORIGINAL)
        self.assertEqual(count, 0)

    def test_function_cases_call_verifier_even_unchanged(self):
        out, count = run_case(self.EQUIV, changed=False, cases=[{"x":1}])
        self.assertEqual(count, 1)
        self.assertEqual(out[0], ORIGINAL)

    def test_function_cases_verifier_error_on_unchanged_code_is_safe(self):
        out, count = run_case(error=RuntimeError(), changed=False, cases=[])
        self.assertEqual(count, 1)
        self.assertEqual(out[0], ORIGINAL)

    def test_six_item_api_contract(self):
        out, _ = run_case(self.EQUIV)
        self.assertEqual(len(out), 6)

    def test_transformer_exception_skips_action(self):
        applied, warnings = [], []
        with patch.object(style_service, '_get_transform_function',
                          return_value=lambda _code: (_ for _ in ()).throw(ValueError('bad'))):
            after, result = style_service._apply_style_action(
                code=ORIGINAL, action_item=ACTION, applied_rules=applied, warnings=warnings)
        self.assertEqual(after, ORIGINAL)
        self.assertEqual(result['status'], 'transformer_error')
        self.assertEqual(applied, [])
        self.assertTrue(warnings)

    def test_bad_verifier_result_preserves_syntax(self):
        out, _ = run_case({"status": "unrecognized"})
        compile(out[0], '<verified>', 'exec')


if __name__ == '__main__':
    unittest.main()
