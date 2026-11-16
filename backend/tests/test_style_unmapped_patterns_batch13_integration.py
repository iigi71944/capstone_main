"""Batch 13 registry, existing metric planning and dispatcher integration."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

import app.services.style_tag_transform_map_service as mapping
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_apply_service import _get_transform_function, _apply_style_action
from app.services.style_transform_audit_service import audit_style_registry


NEW = {
    '문자열 리터럴': ('create_safe_string_literal', 'string_literal_count'),
    '숫자 리터럴': ('create_safe_number_literal', 'number_literal_count'),
    '불리언 리터럴': ('create_safe_boolean_literal', 'boolean_literal_count'),
}


def _plan(style=None, target=None):
    return build_transform_plan({
        'missing_syntax_tags': [], 'missing_concept_tags': [],
        'style_syntax_names': set(), 'style_concept_names': set(),
        'target_syntax_names': set(), 'target_concept_names': set(),
        'style_metrics': style or {},
        'target_analysis': {'metrics': target or {}},
    })


class Batch13IntegrationTests(unittest.TestCase):
    def test_three_new_distinct_links(self):
        for tag, (action, _) in NEW.items():
            with self.subTest(tag=tag):
                self.assertEqual(mapping.get_tag_transform_status(tag), 'linked')
                self.assertEqual(mapping.get_create_action_for_tag(tag), action)
                self.assertTrue(callable(_get_transform_function(action)))

    def test_registry_78_unique_and_24_compare_only(self):
        tree = ast.parse(Path(mapping.__file__).read_text(encoding='utf-8-sig'))
        ds = [node.value for node in tree.body
              if isinstance(node, ast.AnnAssign)
              and isinstance(node.target, ast.Name)
              and node.target.id == 'CREATE_ACTION_BY_TAG']
        self.assertEqual(len(ds), 1)
        keys = [key.value for key in ds[0].keys]
        # CAPSTONE_BATCH19_LEGACY_TEST_V1: later batches may add unique tags.
        self.assertGreaterEqual(len(keys), 78)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(mapping.COMPARE_ONLY_TAGS), 102 - len(keys))
        self.assertEqual(audit_style_registry()['issues'], [])

    def test_existing_metrics_select_only_supported_target(self):
        saved = {metric: 1 for _, metric in NEW.values()}
        target = {'call_count': 3}
        actions = [a['action'] for a in _plan(saved, target)['actions']]
        for action, _ in NEW.values():
            self.assertEqual(actions.count(action), 1)

    def test_missing_saved_preference_or_target_call_not_selected(self):
        saved = {metric: 1 for _, metric in NEW.values()}
        self.assertFalse({v[0] for v in NEW.values()} & {
            a['action'] for a in _plan({}, {'call_count': 3})['actions']})
        self.assertFalse({v[0] for v in NEW.values()} & {
            a['action'] for a in _plan(saved, {})['actions']})

    def test_target_has_literal_already(self):
        style = {metric: 1 for _, metric in NEW.values()}
        target = dict(style, call_count=3)
        self.assertFalse({v[0] for v in NEW.values()} & {
            a['action'] for a in _plan(style, target)['actions']})

    def test_dispatch_performs_real_code_edits(self):
        for tag, code, expected in (
            ('문자열 리터럴', 's = str()\n', "s = ''\n"),
            ('숫자 리터럴', 'n = int()\n', 'n = 0\n'),
            ('불리언 리터럴', 'f = bool()\n', 'f = False\n'),
        ):
            with self.subTest(tag=tag):
                changed, result = _apply_style_action(
                    code=code,
                    action_item={'tag': tag, 'action': NEW[tag][0], 'reason': 'batch13'},
                    applied_rules=[], warnings=[])
                self.assertEqual(result['status'], 'applied')
                self.assertEqual(changed, expected)

    def test_prior_actions_preserved(self):
        baseline = {
            'continue문': 'create_safe_guard_continue',
            '식별 비교': 'create_safe_literal_identity',
            '산술 연산': 'create_safe_arithmetic_expression',
            'len 사용': 'create_safe_literal_len',
            'zip 사용': 'create_safe_literal_zip',
        }
        for tag, action in baseline.items():
            with self.subTest(tag=tag):
                self.assertEqual(mapping.get_create_action_for_tag(tag), action)

    def test_unsafe_tags_remain_compare_only(self):
        for tag in ('await 사용', '전역 변수 사용', '파일 입출력 구조'):
            self.assertEqual(mapping.get_tag_transform_status(tag), 'compare_only')


if __name__ == '__main__':
    unittest.main()
