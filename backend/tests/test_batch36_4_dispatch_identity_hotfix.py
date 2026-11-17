"""Batch36-4 safety regression: canonical dispatch identity + composite fallback."""
from __future__ import annotations

import ast
import importlib.util
import unittest

from tools.fix_batch36_4_dispatch_identity import (
    BAD_MAP, GOOD_MAP, MARKER, NEW_TRY, OLD_TRY, REQUIRED_IMPORT, patch,
)


class PatchContractTests(unittest.TestCase):
    @staticmethod
    def _fixture(newline='\n'):
        source = (
            'from __future__ import annotations\n'
            + 'from app.services.improvement.safe_list_comprehension_service import transform_for_append_to_list_comprehension\n'
            + REQUIRED_IMPORT + '\n'
            + 'def _get_transform_function(action):\n'
            + '    mapping = {' + BAD_MAP + '}\n'
            + '    return mapping.get(action)\n'
            + 'def _apply_style_action(code, action):\n'
            + '    transform_func = transform_for_append_to_list_comprehension\n'
            + OLD_TRY
            + '        pass\n'
            + '    return after\n'
        )
        return source.replace('\n', newline).encode('utf-8')

    def test_old_mapping_to_original_mapping(self):
        updated, status = patch(self._fixture())
        text = updated.decode('utf-8')
        self.assertEqual(status, 'ready')
        self.assertIn(GOOD_MAP, text)
        self.assertNotIn(BAD_MAP, text)
        self.assertEqual(text.count(MARKER), 1)
        self.assertIn(NEW_TRY, text)
        ast.parse(text)

    def test_idempotence(self):
        updated, status = patch(self._fixture())
        self.assertEqual(status, 'ready')
        same, status2 = patch(updated)
        self.assertEqual(status2, 'already_applied')
        self.assertEqual(same, updated)

    def test_windows_crlf_preserved(self):
        updated, status = patch(self._fixture('\r\n'))
        self.assertEqual(status, 'ready')
        self.assertIn(b'\r\n', updated)
        self.assertNotIn(b'\n', updated.replace(b'\r\n', b''))

    def test_refuse_wrong_source(self):
        with self.assertRaises(RuntimeError):
            patch(b'def f():\n    pass\n')

    def test_refuse_missing_import(self):
        with self.assertRaises(RuntimeError):
            patch(self._fixture().replace(REQUIRED_IMPORT.encode(), b'# import removed'))

    def test_refuse_multiple_mappings(self):
        bad = self._fixture() + (BAD_MAP + '\n').encode()
        with self.assertRaises(RuntimeError):
            patch(bad)

    def test_refuse_incomplete_marker(self):
        bad = self._fixture() + ('# ' + MARKER + '\n').encode()
        with self.assertRaises(RuntimeError):
            patch(bad)

    def test_fallback_composes_closed_lambda_and_list(self):
        updated, _ = patch(self._fixture())
        namespace = {}
        exec(updated.decode('utf-8'), namespace)
        sample = ("nums = [1, 2, 3]\n"
                  "inc = lambda x: x + 1\n"
                  "out = []\n"
                  "for x in nums:\n    out.append(inc(x))\n"
                  "print(out)\n")
        result = namespace['_apply_style_action'](
            sample, 'create_safe_comprehension_collection')
        self.assertIn('out = [inc(x) for x in nums]', result)
        self.assertIs(namespace['_get_transform_function'](
            'create_safe_comprehension_collection'),
            namespace['transform_for_append_to_list_comprehension'])

    def test_original_simple_list_transform_stays_canonical(self):
        updated, _ = patch(self._fixture())
        namespace = {}
        exec(updated.decode('utf-8'), namespace)
        sample = ("xs = [1, 2, 3]\nout = []\nfor x in xs:\n"
                  "    out.append(x * 2)\nprint(out)\n")
        expected = namespace['transform_for_append_to_list_comprehension'](sample)
        actual = namespace['_apply_style_action'](
            sample, 'create_safe_comprehension_collection')
        self.assertEqual(actual, expected)
        # The fallback must never change the result returned by the canonical
        # transformer when the latter already produced a rewrite.
        if expected != sample:
            self.assertIn('out = [x * 2 for x in xs]', actual)

    def test_no_mutation_of_input(self):
        original = self._fixture()
        saved = bytes(original)
        patch(original)
        self.assertEqual(original, saved)


_BACKEND = importlib.util.find_spec('app.services.style_diff_service') is not None


@unittest.skipUnless(_BACKEND, 'Requires full FastAPI backend in Docker')
class FullBackendTests(unittest.TestCase):
    def test_dispatcher_identity_restored(self):
        from app.services.style_apply_service import _get_transform_function
        from app.services.improvement.safe_list_comprehension_service import (
            transform_for_append_to_list_comprehension,
        )
        self.assertIs(_get_transform_function('create_safe_comprehension_collection'),
                      transform_for_append_to_list_comprehension)

    def test_composite_R45(self):
        from tools.audit_batch36_1 import evaluate_case
        from tools.batch36_1_cases import CASES
        target = next(case for case in CASES if case.case_id == 'R45')
        result = evaluate_case(target)
        self.assertTrue(result['changed'], result)
        self.assertEqual(result['verification_status'], 'equivalent', result)
        self.assertIn('리스트 컴프리헨션', result['resolved_tags'])
        self.assertIn('컴프리헨션 기반 간결 구조', result['resolved_tags'])

    def test_R08_negative_shape_still_unchanged(self):
        from tools.audit_batch36_1 import evaluate_case
        from tools.batch36_1_cases import CASES
        target = next(case for case in CASES if case.case_id == 'R08')
        result = evaluate_case(target)
        self.assertFalse(result['changed'], result)

    def test_R21_basic_comprehension_is_unchanged_behavior(self):
        from tools.audit_batch36_1 import evaluate_case
        from tools.batch36_1_cases import CASES
        target = next(case for case in CASES if case.case_id == 'R21')
        result = evaluate_case(target)
        self.assertTrue(result['changed'], result)
        self.assertEqual(result['verification_status'], 'equivalent', result)

    def test_R43_keyword_call_unchanged_behavior(self):
        from tools.audit_batch36_1 import evaluate_case
        from tools.batch36_1_cases import CASES
        target = next(case for case in CASES if case.case_id == 'R43')
        result = evaluate_case(target)
        self.assertTrue(result['changed'], result)
        self.assertEqual(result['verification_status'], 'equivalent', result)

    def test_strict_unverified_async_still_rolled_back(self):
        from tools.audit_batch36_1 import evaluate_case
        from tools.batch36_1_cases import CASES
        for target in CASES:
            if target.case_id in {'R04', 'R05', 'R06'}:
                with self.subTest(case=target.case_id):
                    result = evaluate_case(target, strict_runtime_validation=True)
                    self.assertFalse(result['changed'], result)


if __name__ == '__main__':
    unittest.main()
