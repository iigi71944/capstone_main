"""36-2 regression: safe one-time-bound string receiver + audit integrity.

No executable user fixture is evaluated outside the existing engine. Tests
assert syntax, round-trip behavior, rebind rejections and strict-mode rollback.
"""
import ast
import copy
import importlib.util
import unittest

from app.services.improvement.safe_batch29_service import (
    transform_strip_explicit_none_default,
    transform_strip_implicit_none_default,
    transform_sorted_explicit_reverse_default,
    transform_sorted_implicit_reverse_default,
)
from tools.audit_batch36_1 import evaluate_case
from tools.audit_batch36_2 import (
    ASYNC_CASES, STRIP_CASES, classify_unchanged, validate_baseline,
)
from tools.batch36_1_cases import CASES


class NamedStringReceiverTests(unittest.TestCase):
    def test_literal_receiver_still_supported(self):
        source = "out = ' hello '.strip()\nprint(out)\n"
        output = transform_strip_explicit_none_default(source)
        self.assertEqual(output, "out = ' hello '.strip(None)\nprint(out)\n")
        self.assertEqual(transform_strip_implicit_none_default(output), source)

    def test_named_receiver_explicit(self):
        source = "word = '  hello  '\nout = word.strip()\nprint(out)\n"
        transformed = transform_strip_explicit_none_default(source)
        self.assertEqual(transformed, "word = '  hello  '\nout = word.strip(None)\nprint(out)\n")
        self.assertEqual(transform_strip_implicit_none_default(transformed), source)

    def test_named_receiver_implicit(self):
        source = "word = '  hello  '\nout = word.strip(None)\nprint(out)\n"
        self.assertEqual(transform_strip_implicit_none_default(source),
                         "word = '  hello  '\nout = word.strip()\nprint(out)\n")

    def test_three_assignments_and_unrelated_strings(self):
        source = "word = '  A  '\nother = '  B  '\na = word.strip()\nb = other.strip()\nprint(a, b)\n"
        after = transform_strip_explicit_none_default(source)
        self.assertIn('a = word.strip(None)', after)
        self.assertIn('b = other.strip(None)', after)
        self.assertEqual(transform_strip_implicit_none_default(after), source)

    def test_unicode_and_crlf_preserved(self):
        source = "word = '  한글✨  '\r\nout = word.strip()\r\nprint(out)\r\n"
        target = transform_strip_explicit_none_default(source)
        self.assertIn('word.strip(None)\r\n', target)
        self.assertEqual(target.count('\r\n'), source.count('\r\n'))
        self.assertEqual(transform_strip_implicit_none_default(target), source)

    def test_original_literal_and_sorted_transforms_unchanged(self):
        code = "out = sorted([3, 1])\nprint(out)\n"
        converted = transform_sorted_explicit_reverse_default(code)
        self.assertIn('reverse=False', converted)
        self.assertEqual(transform_sorted_implicit_reverse_default(converted), code)

    def test_rebinding_refused(self):
        source = "word = ' hi '\nword = ' bye '\nout = word.strip()\nprint(out)\n"
        self.assertEqual(transform_strip_explicit_none_default(source), source)

    def test_delete_refused(self):
        source = "word = ' hi '\ndel word\nout = word.strip()\n"
        self.assertEqual(transform_strip_explicit_none_default(source), source)

    def test_variable_initialised_from_function_refused(self):
        source = "word = str(' hello ')\nout = word.strip()\n"
        self.assertEqual(transform_strip_explicit_none_default(source), source)

    def test_variable_initialised_after_call_refused(self):
        source = "out = word.strip()\nword = 'hi'\n"
        self.assertEqual(transform_strip_explicit_none_default(source), source)

    def test_function_scope_refused(self):
        source = "def example():\n    word = 'hi'\n    return word.strip()\n"
        self.assertEqual(transform_strip_explicit_none_default(source), source)

    def test_subscript_or_object_receiver_refused(self):
        source = "words = [' hi ']\nout = words[0].strip()\n"
        self.assertEqual(transform_strip_explicit_none_default(source), source)

    def test_import_and_dynamic_execution_refused(self):
        for source in (
            "import builtins\nword = ' a '\nout = word.strip()\n",
            "word = ' a '\neval('2 + 2')\nout = word.strip()\n",
            "word = ' a '\nglobals()['word'] = ' b '\nout = word.strip()\n",
        ):
            with self.subTest(source=source):
                self.assertEqual(transform_strip_explicit_none_default(source), source)

    def test_assignment_in_conditional_refused(self):
        source = "if True:\n    word = 'hi'\nout = word.strip()\n"
        self.assertEqual(transform_strip_explicit_none_default(source), source)

    def test_assignment_alias_refused(self):
        source = "word = alias = ' hello '\nout = word.strip()\n"
        self.assertEqual(transform_strip_explicit_none_default(source), source)

    def test_no_mutation_and_syntax(self):
        code = "word = ' hi '\nout = word.strip()\n"
        orig = str(code)
        after = transform_strip_explicit_none_default(code)
        self.assertEqual(code, orig)
        ast.parse(after)


class Batch36InstallerTests(unittest.TestCase):
    def test_installer_handles_lf_and_crlf_without_rewriting_unrelated_source(self):
        from tools.apply_batch36_2 import _patch, OLD_CALL, INSERT_BEFORE
        fake = 'from __future__ import annotations\nimport ast\n\n' + INSERT_BEFORE + OLD_CALL + '    return code\n'
        for newline in ('\n', '\r\n'):
            with self.subTest(newline=repr(newline)):
                source = fake.replace('\n', newline).encode('utf-8')
                patched, status = _patch(source)
                self.assertEqual(status, 'ready')
                self.assertEqual(patched.count(b'CAPSTONE_BATCH36_2_SAFE_NAMED_STRIP_V1'), 1)
                if newline == '\r\n':
                    self.assertEqual(patched.count(b'\r\n'), patched.count(b'\n'))
                else:
                    self.assertNotIn(b'\r\n', patched)
                unchanged, status2 = _patch(patched)
                self.assertEqual(status2, 'already_applied')
                self.assertEqual(unchanged, patched)

    def test_installer_refuses_unknown_source(self):
        from tools.apply_batch36_2 import _patch
        with self.assertRaises(RuntimeError):
            _patch(b'def wrong(): pass\n')


class Batch36AuditTests(unittest.TestCase):
    def test_benchmark_case_ids_stable(self):
        self.assertEqual(len(CASES), 50)
        self.assertEqual([x.case_id for x in CASES if x.case_id in STRIP_CASES], list(STRIP_CASES))
        self.assertEqual([x.case_id for x in CASES if x.case_id in ASYNC_CASES], list(ASYNC_CASES))

    def test_validate_baseline_exact_ids(self):
        good = {'report_version': 1, 'cases': [{'id': x.case_id} for x in CASES]}
        self.assertEqual(len(validate_baseline(good)), 50)
        broken = copy.deepcopy(good)
        broken['cases'][2]['id'] = 'wrong'
        with self.assertRaises(ValueError):
            validate_baseline(broken)
        with self.assertRaises(ValueError):
            validate_baseline({'report_version': 2, 'cases': good['cases']})

    def test_classification_never_calls_expected_skips_a_failure(self):
        self.assertEqual(classify_unchanged({'changed': False, 'initial_missing_count': 0}),
                         'already_no_missing_tag')
        self.assertEqual(classify_unchanged({'id': 'R09', 'changed': False,
                                              'initial_missing_count': 3}),
                         'intentional_negative_shape')
        self.assertEqual(classify_unchanged({'id': 'R20', 'changed': False,
                                              'initial_missing_count': 3}),
                         'insufficient_preference_evidence')
        self.assertEqual(classify_unchanged({'id': 'R43', 'changed': False,
                                              'initial_missing_count': 1}),
                         'unresolved_safe_pattern_or_style_gap')

    def test_four_repaired_cases_through_actual_style_engine(self):
        if importlib.util.find_spec("app.services.style_diff_service") is None:
            self.skipTest("전체 백엔드 서비스가 없는 독립 검사 환경")
        for case in CASES:
            if case.case_id not in STRIP_CASES:
                continue
            with self.subTest(case=case.case_id):
                row = evaluate_case(case)
                self.assertFalse(row['errors'], row)
                self.assertTrue(row['changed'], row)
                self.assertEqual(row['verification_status'], 'equivalent', row)
                self.assertIs(row['verification_equivalent'], True)
                self.assertIn('strip(', row['diff_excerpt'])

    def test_async_remains_blocked_and_strict_mode_rolls_back(self):
        if importlib.util.find_spec("app.services.style_diff_service") is None:
            self.skipTest("전체 백엔드 서비스가 없는 독립 검사 환경")
        for case in CASES:
            if case.case_id not in ASYNC_CASES:
                continue
            with self.subTest(case=case.case_id):
                row = evaluate_case(case, strict_runtime_validation=True)
                self.assertFalse(row['errors'], row)
                self.assertFalse(row['changed'], row)
                self.assertEqual(row['verification_status'], 'not_verified', row)
                self.assertIsNone(row['verification_equivalent'])
                self.assertTrue(any('취소' in w or '원본' in w for w in row['warnings']))


if __name__ == '__main__':
    unittest.main()
