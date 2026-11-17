"""Batch 34: planned action, real applicator, and strict rollback regression.

The fixed source snippets are trusted test fixtures, never user submissions.
Both the public saved-tag spelling and the safe planned action are checked.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.style_apply_service import _apply_style_action, apply_coding_style
from app.services.style_tag_transform_map_service import CREATE_ACTION_BY_TAG
from app.services.style_transform_plan_service import build_transform_plan
from app.services.tag_rule_service import SYNTAX_TAG_RULES, CONCEPT_TAG_RULES
from tools.audit_transform_batch34 import (
    EXPECTED_ACTIONS,
    TRUSTED_BASIC,
    fixture_diff,
    probe_pipeline,
)


class RoutingSafetyTests(unittest.TestCase):
    def test_01_six_still_have_public_registry_names(self):
        for tag in EXPECTED_ACTIONS:
            with self.subTest(tag=tag):
                self.assertIn(tag, CREATE_ACTION_BY_TAG)
        self.assertEqual(len(CREATE_ACTION_BY_TAG), 102)

    def test_02_dictionary_is_selected_as_safe_action_not_legacy(self):
        tag = '딕셔너리 컴프리헨션'
        self.assertEqual(CREATE_ACTION_BY_TAG[tag], 'create_dict_comprehension')
        actions = build_transform_plan(fixture_diff(tag))['actions']
        self.assertEqual([x['action'] for x in actions], ['create_safe_dict_comprehension'])

    def test_03_no_style_preference_has_no_actions(self):
        actions = build_transform_plan(fixture_diff(()))['actions']
        self.assertEqual(actions, [])

    def test_04_opposite_list_preferences_are_not_guessed(self):
        plan = build_transform_plan(fixture_diff(('리스트 누적 방식 사용', '리스트 컴프리헨션')))
        actions = {x['action'] for x in plan['actions']}
        self.assertFalse(actions & {'create_safe_append_collection', 'create_safe_comprehension_collection'})

    def test_05_opposite_loop_preferences_are_not_guessed(self):
        plan = build_transform_plan(fixture_diff(('인덱스 기반 반복 사용', '직접 반복 사용')))
        actions = {x['action'] for x in plan['actions']}
        self.assertFalse(actions & {'create_index_iteration', 'create_direct_iteration'})

    def test_06_unsafe_runtime_result_rolls_back_to_original(self):
        tag = '딕셔너리 컴프리헨션'
        code = TRUSTED_BASIC[tag]
        with patch('app.services.style_apply_service.compare_style_with_target_code', return_value=fixture_diff(tag)), \
             patch('app.services.style_apply_service.compare_after_transform', return_value={
                 'missing_syntax_tags': [], 'missing_concept_tags': []
             }), \
             patch('app.services.style_apply_service.verify_execution_equivalence', return_value={
                 'status': 'different', 'equivalent': False, 'message': '테스트 전용 검증 실패'
             }):
            output, summary, applied, warnings, _, verified = apply_coding_style(
                code, style={}, strict_runtime_validation=True
            )
        self.assertEqual(output, code)
        self.assertEqual(applied, [])
        self.assertEqual(verified.get('status'), 'different')
        self.assertTrue(warnings)


def _test_real_path(self, tag):
    report = probe_pipeline(tag, TRUSTED_BASIC[tag])
    self.assertTrue(report['selected_action_matches_expected'], report)
    self.assertTrue(report['selected_action_is_registered'], report)
    self.assertEqual(report['direct_action_status'], 'applied', report)
    self.assertTrue(report['direct_source_changed'], report)
    self.assertTrue(report['direct_python_valid'], report)
    self.assertEqual(report['strict_pipeline_verdict'], 'equivalent', report)
    self.assertTrue(report['strict_pipeline_changed'], report)
    self.assertTrue(report['strict_pipeline_applied_note'], report)
    self.assertEqual(report['errors'], [], report)


def _test_invalid_python(self, tag):
    plan = build_transform_plan(fixture_diff(tag))
    chosen = [item for item in plan['actions'] if item['tag'] == tag]
    self.assertEqual(len(chosen), 1, (tag, plan))
    bad = 'for item in range(:\n  print(item)\n'
    out, ledger = _apply_style_action(
        code=bad, action_item=chosen[0], applied_rules=[], warnings=[]
    )
    self.assertEqual(out, bad, tag)
    self.assertNotEqual(ledger['status'], 'applied', tag)


for _i, _tag in enumerate(EXPECTED_ACTIONS, 1):
    def _real(self, tag=_tag):
        _test_real_path(self, tag)
    _real.__name__ = f'test_real_path_{_i:02d}'
    setattr(RoutingSafetyTests, _real.__name__, _real)

    def _invalid(self, tag=_tag):
        _test_invalid_python(self, tag)
    _invalid.__name__ = f'test_invalid_python_{_i:02d}'
    setattr(RoutingSafetyTests, _invalid.__name__, _invalid)

del _i, _tag, _real, _invalid


if __name__ == '__main__':
    unittest.main()
