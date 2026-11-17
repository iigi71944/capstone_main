"""36-5 final evidence tests; previous transformation contracts remain unchanged."""
from __future__ import annotations

import ast
from copy import deepcopy
import importlib.util
import json
import unittest

from app.services.style_alignment_quality_service import (
    QUALITY_VERSION, build_style_alignment_quality,
)
from tools.apply_batch36_5 import MARKER, patch, OLD_IMPORT, OLD_BLOCK
from tools.audit_batch36_5 import (
    MIN_EXAMPLES, validate_baseline, make_report, collect_verified_examples,
)
from tools.batch36_1_cases import CASES


def example_diff(*, syntax=(), concept=(), metrics=None, style=None, complete=True):
    return {
        'missing_syntax_tags': [{'tag': name} for name in syntax],
        'missing_concept_tags': [{'tag': name} for name in concept],
        'target_analysis': {'metrics': metrics or {}},
        'style_metrics': style or {},
        'style_metrics_info': {
            'status': 'current_complete' if complete else 'legacy_complete',
            'stored_version': 1 if complete else None,
            'automatic_transforms_allowed': True,
        },
    }


def verified():
    return {'status': 'equivalent', 'equivalent': True}


def fake_base():
    return {
        'report_version': 1,
        'current': {'changed': 36, 'verified_changes': 33,
                    'no_safe_pattern': 55, 'preflight_skipped': 21,
                    'failed_cases': []},
        'strict': {'unverified_changed_cases': [], 'failed_cases': []},
        'contract': {'same_50_ids': True, 'strict_unverified_changed_cases': []},
        'composite_R45': {'changed': True, 'verification_status': 'equivalent'},
    }


class QualityEvidenceTests(unittest.TestCase):
    def test_version_is_stable(self):
        self.assertEqual(QUALITY_VERSION, 1)

    def test_tag_resolved_and_introduced_distinct(self):
        before = example_diff(syntax=('A', 'B'), concept=('C',))
        after = example_diff(syntax=('B', 'D'), concept=('C',))
        q = build_style_alignment_quality(initial_diff=before, final_diff=after,
                                          execution_verification=verified(), code_changed=True)
        self.assertEqual(q['tag_gap']['before'], 3)
        self.assertEqual(q['tag_gap']['after'], 3)
        self.assertEqual(q['tag_gap']['resolved'], [{'family': 'syntax', 'tag': 'A'}])
        self.assertEqual(q['tag_gap']['introduced'], [{'family': 'syntax', 'tag': 'D'}])
        self.assertEqual(q['conclusion'], 'verified_observed_progress')

    def test_concept_and_syntax_names_do_not_collapse(self):
        before = example_diff(syntax=('same',), concept=('same',))
        after = example_diff()
        q = build_style_alignment_quality(initial_diff=before, final_diff=after,
                                          execution_verification=verified(), code_changed=True)
        self.assertEqual(q['tag_gap']['resolved_count'], 2)

    def test_empty_diffs_are_unchanged(self):
        q = build_style_alignment_quality(initial_diff=example_diff(), final_diff=example_diff(),
                                          execution_verification=None, code_changed=False)
        self.assertEqual(q['tag_gap']['resolved_count'], 0)
        self.assertEqual(q['conclusion'], 'unchanged')
        self.assertIsNone(q['observed_runtime_equivalent'])

    def test_verifier_not_verified_cannot_count_as_progress(self):
        q = build_style_alignment_quality(initial_diff=example_diff(syntax=('A',)),
            final_diff=example_diff(), execution_verification={'status': 'not_verified', 'equivalent': None},
            code_changed=True)
        self.assertEqual(q['conclusion'], 'changed_not_verified')
        self.assertIs(q['observed_runtime_equivalent'], False)

    def test_known_difference_never_counts_as_equivalent(self):
        q = build_style_alignment_quality(initial_diff=example_diff(syntax=('A',)),
            final_diff=example_diff(), execution_verification={'status': 'different', 'equivalent': False},
            code_changed=True)
        self.assertFalse(q['observed_runtime_equivalent'])

    def test_contradictory_verifier_not_counted(self):
        q = build_style_alignment_quality(initial_diff=example_diff(),
            final_diff=example_diff(), execution_verification={'status': 'equivalent', 'equivalent': None},
            code_changed=True)
        self.assertEqual(q['conclusion'], 'changed_not_verified')

    def test_verified_change_without_measured_progress_is_honest(self):
        q = build_style_alignment_quality(initial_diff=example_diff(),
            final_diff=example_diff(), execution_verification=verified(), code_changed=True)
        self.assertEqual(q['conclusion'], 'verified_change_without_measured_progress')

    def test_preference_explicit_improves_separately_from_tags(self):
        stored = {'sorted_reverse_false_explicit_count': 3, 'sorted_reverse_false_implicit_count': 1}
        before = example_diff(metrics={'sorted_reverse_false_explicit_count': 0,
                                        'sorted_reverse_false_implicit_count': 1}, style=stored)
        after = example_diff(syntax=('불리언 리터럴',),
            metrics={'sorted_reverse_false_explicit_count': 1,
                     'sorted_reverse_false_implicit_count': 0}, style=stored)
        q = build_style_alignment_quality(initial_diff=before, final_diff=after,
                                          execution_verification=verified(), code_changed=True)
        self.assertEqual(q['default_form_preferences']['improved'], 1)
        self.assertEqual(q['tag_gap']['introduced_count'], 1)
        self.assertEqual(q['conclusion'], 'verified_observed_progress')

    def test_preference_implicit_improves_with_none_tag_loss(self):
        stored = {'strip_none_explicit_count': 1, 'strip_none_implicit_count': 3}
        before = example_diff(metrics={'strip_none_explicit_count': 1,
                                        'strip_none_implicit_count': 0}, style=stored)
        after = example_diff(syntax=('None 사용',),
            metrics={'strip_none_explicit_count': 0,
                     'strip_none_implicit_count': 1}, style=stored)
        q = build_style_alignment_quality(initial_diff=before, final_diff=after,
                                          execution_verification=verified(), code_changed=True)
        self.assertEqual(q['default_form_preferences']['improved'], 1)
        self.assertEqual(q['tag_gap']['introduced_count'], 1)

    def test_preference_regression_is_reported(self):
        stored = {'sorted_reverse_false_explicit_count': 4, 'sorted_reverse_false_implicit_count': 0}
        before = example_diff(metrics={'sorted_reverse_false_explicit_count': 1,
                                        'sorted_reverse_false_implicit_count': 0}, style=stored)
        after = example_diff(metrics={'sorted_reverse_false_explicit_count': 0,
                                      'sorted_reverse_false_implicit_count': 1}, style=stored)
        q = build_style_alignment_quality(initial_diff=before, final_diff=after,
                                          execution_verification=verified(), code_changed=True)
        self.assertEqual(q['default_form_preferences']['regressed'], 1)

    def test_preference_tie_is_not_inferred(self):
        stored = {'sorted_reverse_false_explicit_count': 2, 'sorted_reverse_false_implicit_count': 2}
        q = build_style_alignment_quality(initial_diff=example_diff(metrics=stored, style=stored),
            final_diff=example_diff(metrics=stored, style=stored),
            execution_verification=verified(), code_changed=True)
        self.assertEqual(q['default_form_preferences']['evaluated'], 0)

    def test_missing_metric_is_unknown_not_zero(self):
        before = example_diff(metrics={'strip_none_implicit_count': 1},
                              style={'strip_none_explicit_count': 3, 'strip_none_implicit_count': 1})
        q = build_style_alignment_quality(initial_diff=before,
            final_diff=example_diff(metrics={'strip_none_explicit_count': 2}),
            execution_verification=verified(), code_changed=True)
        self.assertEqual(q['default_form_preferences']['evaluated'], 0)

    def test_boolean_metric_not_integer(self):
        before = example_diff(metrics={'strip_none_explicit_count': False,
                                       'strip_none_implicit_count': 1},
            style={'strip_none_explicit_count': 3, 'strip_none_implicit_count': 1})
        q = build_style_alignment_quality(initial_diff=before,
            final_diff=example_diff(metrics={'strip_none_explicit_count': 1, 'strip_none_implicit_count': 0}),
            execution_verification=verified(), code_changed=True)
        self.assertEqual(q['default_form_preferences']['evaluated'], 0)

    def test_legacy_metrics_are_not_assumed_current(self):
        before = example_diff(metrics={'strip_none_explicit_count': 3,
                                       'strip_none_implicit_count': 1}, complete=False)
        q = build_style_alignment_quality(initial_diff=before,
            final_diff=example_diff(), execution_verification=verified(), code_changed=True)
        self.assertEqual(q['default_form_preferences']['status'], 'unavailable')

    def test_nonmutation_and_json_serialization(self):
        before = example_diff(syntax=('a',), concept=('b',))
        after = example_diff(syntax=('b',), concept=('c',))
        old = deepcopy((before, after))
        q = build_style_alignment_quality(initial_diff=before, final_diff=after,
                                          execution_verification=verified(), code_changed=True)
        self.assertEqual((before, after), old)
        self.assertEqual(json.loads(json.dumps(q, ensure_ascii=False))['version'], 1)

    def test_invalid_container_rejected(self):
        with self.assertRaises(TypeError):
            build_style_alignment_quality(initial_diff=None, final_diff={},
                                          execution_verification=None, code_changed=False)


class InstallerContractTests(unittest.TestCase):
    def setUp(self):
        self.source = (OLD_IMPORT + '\n'
                       + 'def f():\n'
                       + '    final_diff = {}\n'
                       + '    initial_diff = {}\n'
                       + '    code = ""\n'
                       + '    transformed_code = ""\n'
                       + '    transform_plan = {}\n'
                       + '    action_results = []\n'
                       + '    execution_verification = None\n'
                       + OLD_BLOCK + '    return final_diff\n')

    def test_patch_idempotence(self):
        patched, status = patch(self.source.encode('utf-8'))
        self.assertEqual(status, 'ready')
        self.assertIn(MARKER.encode('utf-8'), patched)
        ast.parse(patched)
        second, result = patch(patched)
        self.assertEqual(result, 'already_applied')
        self.assertEqual(second, patched)

    def test_crlf_preserved(self):
        src = self.source.replace('\n', '\r\n').encode('utf-8')
        after, result = patch(src)
        self.assertEqual(result, 'ready')
        self.assertNotIn(b'\n', after.replace(b'\r\n', b''))

    def test_wrong_anchor_refused(self):
        with self.assertRaises(RuntimeError):
            patch(b'def wrong():\n    return None\n')

    def test_double_anchor_refused(self):
        broken = self.source.replace(OLD_IMPORT, OLD_IMPORT + OLD_IMPORT)
        with self.assertRaises(RuntimeError):
            patch(broken.encode('utf-8'))


class AuditContractsTests(unittest.TestCase):
    def test_50_case_catalog_is_stable(self):
        self.assertEqual(len(CASES), 50)
        self.assertEqual([c.case_id for c in CASES], [f'R{i:02d}' for i in range(1, 51)])

    def test_baseline_valid(self):
        self.assertEqual(validate_baseline(fake_base())['verified_changes'], 33)

    def test_baseline_rejects_failed_validation(self):
        bad = fake_base()
        bad['strict']['unverified_changed_cases'] = ['R04']
        with self.assertRaises(ValueError):
            validate_baseline(bad)

    def test_baseline_rejects_bad_composite(self):
        bad = fake_base()
        bad['composite_R45']['verification_status'] = 'not_verified'
        with self.assertRaises(ValueError):
            validate_baseline(bad)

    def test_minimum_export_count(self):
        self.assertGreaterEqual(MIN_EXAMPLES, 30)


@unittest.skipUnless(importlib.util.find_spec('app.services.style_diff_service'),
                     'Full backend is required for integration checks')
class ProductionIntegrationTests(unittest.TestCase):
    def test_R08_no_op_and_quality(self):
        from app.services.style_diff_service import analyze_code_style
        from app.services.style_apply_service import apply_coding_style
        case = next(c for c in CASES if c.case_id == 'R08')
        analysis = analyze_code_style(case.style_code)
        style = {'id': 'R08', 'name': 'r08', 'description': 'test',
                 'syntax_tags': analysis['syntax_tags'], 'concept_tags': analysis['concept_tags'],
                 'metrics': analysis['metrics'], 'metrics_version': 1, 'created_at': 'now'}
        code, _, _, _, diff, _ = apply_coding_style(code=case.target_code, style=style)
        self.assertEqual(code, case.target_code)
        self.assertEqual(diff['style_alignment_quality']['conclusion'], 'unchanged')

    def test_R17_metric_preference_with_tag_drift(self):
        from app.services.style_diff_service import analyze_code_style
        from app.services.style_apply_service import apply_coding_style
        case = next(c for c in CASES if c.case_id == 'R17')
        analysis = analyze_code_style(case.style_code)
        style = {'id': 'R17', 'name': 'r17', 'description': 'test',
                 'syntax_tags': analysis['syntax_tags'], 'concept_tags': analysis['concept_tags'],
                 'metrics': analysis['metrics'], 'metrics_version': 1, 'created_at': 'now'}
        code, _, _, _, diff, ver = apply_coding_style(code=case.target_code, style=style)
        self.assertNotEqual(code, case.target_code)
        self.assertEqual(ver['status'], 'equivalent')
        quality = diff['style_alignment_quality']
        self.assertEqual(quality['default_form_preferences']['improved'], 1)
        self.assertGreaterEqual(quality['tag_gap']['introduced_count'], 1)

    def test_R43_R45_verified(self):
        from tools.audit_batch36_1 import evaluate_case
        for case in CASES:
            if case.case_id in {'R43', 'R45'}:
                with self.subTest(case=case.case_id):
                    row = evaluate_case(case, strict_runtime_validation=True)
                    self.assertTrue(row['changed'], row)
                    self.assertEqual(row['verification_status'], 'equivalent', row)

    def test_strict_export_has_30_or_more_real_changes(self):
        from tools.audit_batch36_1 import run_audit
        report = run_audit(CASES, strict_runtime_validation=True)
        examples = collect_verified_examples(report)
        self.assertGreaterEqual(len(examples), 30)
        self.assertTrue(any(row['id'] == 'R45' for row in examples))
        self.assertTrue(all(row['actual_transformed_code'] != row['target_source_code']
                            for row in examples))
        self.assertTrue(all(row['execution_verification_status'] == 'equivalent'
                            for row in examples))
        self.assertTrue(all(row['quality_evidence']['version'] == QUALITY_VERSION
                            for row in examples))


if __name__ == '__main__':
    unittest.main()
