"""Tests for the read-only, fixed-fixture style runtime audit.

Run from capstone_main/backend:
    python -m unittest discover -s tests -p "test_style_runtime_audit_upgrade.py" -v
"""

import json
import unittest
from unittest.mock import patch

from app.services import style_runtime_audit_service as audit


class FixedRuntimeFixtures(unittest.TestCase):
    def test_unique_probe_names(self):
        names = [probe.name for probe in audit.PROBES]
        self.assertEqual(len(names), len(set(names)))

    def test_probes_have_finite_actions(self):
        self.assertEqual({p.action for p in audit.PROBES}, set(audit._TRANSFORMS))

    def test_report_is_json_serializable(self):
        report = audit.run_runtime_audit()
        self.assertIsInstance(json.loads(json.dumps(report, ensure_ascii=False)), dict)

    def test_report_matches_probe_count(self):
        report = audit.run_runtime_audit()
        s = report['summary']
        self.assertEqual(s['total'], len(audit.PROBES))
        self.assertEqual(s['passed'] + s['failed'], s['total'])

    def test_no_external_user_code_in_report(self):
        report = audit.run_runtime_audit()
        self.assertIn('고정', report['note'])

    def test_unknown_action_is_rejected(self):
        p = audit.Probe('bad-action', 'not_registered', 'x = 1', False)
        result = audit.check_probe(p)
        self.assertFalse(result['ok'])

    def test_detects_output_divergence(self):
        probe = audit.Probe('mismatch', 'create_safe_append_collection',
                            'result = [x + 1 for x in [1, 2]]\n__audit_result__ = result\n', True)
        with patch.dict(audit._TRANSFORMS, {
            'create_safe_append_collection': lambda s: 'result = [9, 9]\n__audit_result__ = result\n',
        }):
            result = audit.check_probe(probe)
        self.assertFalse(result['ok'])
        self.assertFalse(result['checks']['stdout_exception_result_equal'])

    def test_detects_missing_required_change(self):
        probe = audit.Probe('skipped', 'create_safe_append_collection',
                            'result = [x for x in [1, 2]]\n__audit_result__ = result\n', True)
        with patch.dict(audit._TRANSFORMS, {
            'create_safe_append_collection': lambda source: source,
        }):
            result = audit.check_probe(probe)
        self.assertFalse(result['ok'])
        self.assertFalse(result['checks']['changed_expected'])

    def test_detects_syntax_error_in_result(self):
        probe = audit.Probe('invalid', 'create_safe_append_collection',
                            'result = [x for x in [1, 2]]\n', True)
        with patch.dict(audit._TRANSFORMS, {
            'create_safe_append_collection': lambda _: 'for bad',
        }):
            result = audit.check_probe(probe)
        self.assertFalse(result['ok'])
        self.assertIn('SyntaxError', result['error'])

    def test_detects_unexpected_unsafe_transformation(self):
        probe = audit.Probe('should-not-change', 'create_safe_comprehension_collection',
                            'result=[]\nfor x in [1]:\n    # keep\n    result.append(x)\n', False)
        with patch.dict(audit._TRANSFORMS, {
            'create_safe_comprehension_collection': lambda _:
                'result=[x for x in [1]]\n',
        }):
            result = audit.check_probe(probe)
        self.assertFalse(result['ok'])
        self.assertFalse(result['checks']['changed_expected'])

    def test_all_built_in_probes_pass(self):
        report = audit.run_runtime_audit()
        self.assertEqual(report['status'], 'ok', report['failures'])


if __name__ == '__main__':
    unittest.main()
