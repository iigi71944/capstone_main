"""Tests for the additive, read-only full-feature curated fixture audit."""

import json
import unittest
from unittest.mock import patch

from app.services import style_feature_coverage_audit_service as audit
from app.services.style_tag_transform_map_service import get_tag_transform_status


class FullFeatureCoverageAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = audit.audit_full_feature_coverage()

    def test_all_eighteen_tags_present(self):
        self.assertEqual(len(audit._EXAMPLES), 18)

    def test_tag_names_unique(self):
        tags = [case.tag for case in audit._EXAMPLES]
        self.assertEqual(len(tags), len(set(tags)))

    def test_all_eighteen_tags_are_linked(self):
        for case in audit._EXAMPLES:
            with self.subTest(tag=case.tag):
                self.assertEqual(get_tag_transform_status(case.tag), 'linked')

    def test_report_success_status(self):
        self.assertEqual(self.report['status'], 'ok', self.report)

    def test_positive_count(self):
        self.assertEqual(self.report['summary']['positive_cases'], 18)

    def test_negative_count(self):
        self.assertEqual(self.report['summary']['negative_cases'], 14)

    def test_no_failed_cases(self):
        self.assertEqual(self.report['summary']['failed'], 0)

    def test_every_positive_dispatch_selected(self):
        for row in self.report['positive']:
            with self.subTest(tag=row['tag']):
                self.assertTrue(row['selected_action'])

    def test_every_positive_changes_code(self):
        for row in self.report['positive']:
            with self.subTest(tag=row['tag']):
                self.assertTrue(row['changed'])

    def test_every_positive_same_observed_behavior(self):
        for row in self.report['positive']:
            with self.subTest(tag=row['tag']):
                self.assertIs(row['equivalent'], True)

    def test_all_dangerous_patterns_are_skipped(self):
        for row in self.report['negative']:
            with self.subTest(case=row['case']):
                self.assertEqual(row['status'], 'passed', row)

    def test_json_serializable(self):
        output = json.loads(json.dumps(self.report, ensure_ascii=False))
        self.assertEqual(output['summary']['failed'], 0)

    def test_malformed_tag_mapping_reported(self):
        with patch.object(audit, 'get_create_action_for_tag', return_value='bad_action'):
            report = audit.audit_full_feature_coverage()
        self.assertEqual(report['status'], 'issues_found')
        self.assertTrue(any('액션 매핑 불일치' in str(r['reasons']) for r in report['positive']))

    def test_missing_dispatcher_reported(self):
        with patch.object(audit, '_get_transform_function', return_value=None):
            report = audit.audit_full_feature_coverage()
        self.assertEqual(report['status'], 'issues_found')
        self.assertTrue(any('변환 실행 함수 연결 누락' in str(r['reasons']) for r in report['positive']))

    def test_bad_plan_reported(self):
        with patch.object(audit, '_plan_for_single_tag', return_value={'actions': []}):
            report = audit.audit_full_feature_coverage()
        self.assertEqual(report['status'], 'issues_found')
        self.assertTrue(any(not r['selected_action'] for r in report['positive']))

    def test_invalid_result_reported(self):
        with patch.object(audit, '_get_transform_function', return_value=lambda _: 'def broken('):
            report = audit.audit_full_feature_coverage()
        self.assertEqual(report['status'], 'issues_found')
        self.assertTrue(report['summary']['failed'] > 0)

    def test_non_string_result_reported(self):
        with patch.object(audit, '_get_transform_function', return_value=lambda _: None):
            report = audit.audit_full_feature_coverage()
        self.assertEqual(report['status'], 'issues_found')
        self.assertTrue(any('문자열이 아님' in str(r['reasons']) for r in report['positive']))

    def test_noop_result_reported(self):
        with patch.object(audit, '_get_transform_function', return_value=lambda code: code):
            report = audit.audit_full_feature_coverage()
        self.assertEqual(report['status'], 'issues_found')
        self.assertTrue(any(not r['changed'] for r in report['positive']))

    def test_behavior_mismatch_reported(self):
        func = audit._get_transform_function(audit._EXAMPLES[0].action)
        # Only the set-comp transform is patched, returning syntactically valid
        # output with the expected marker but deliberately different behavior.
        invalid = lambda code: 'result = {0 for x in [1,2,3]}\n'
        real = audit._get_transform_function
        def dispatcher(action):
            return invalid if action == audit._EXAMPLES[0].action else real(action)
        with patch.object(audit, '_get_transform_function', side_effect=dispatcher):
            report = audit.audit_full_feature_coverage()
        self.assertEqual(report['status'], 'issues_found')
        self.assertIs(report['positive'][0]['equivalent'], False)

    def test_unsafe_skip_failure_detected(self):
        actual = audit._get_transform_function
        def bad_dispatcher(action):
            if action == 'create_safe_explicit_class':
                return lambda code: code + '\n# changed\n'
            return actual(action)
        with patch.object(audit, '_get_transform_function', side_effect=bad_dispatcher):
            report = audit.audit_full_feature_coverage()
        self.assertEqual(report['status'], 'issues_found')
        self.assertTrue(any(r['status']=='failed' and r['action']=='create_safe_explicit_class'
                            for r in report['negative']))


if __name__ == '__main__':
    unittest.main()
