"""Batch 12 registry/plan/dispatcher safety and compatibility checks."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

import app.services.style_tag_transform_map_service as mapping
from app.services.style_tag_transform_map_service import (
    get_create_action_for_tag, get_tag_transform_status,
)
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_apply_service import _get_transform_function, _apply_style_action
from app.services.style_transform_audit_service import audit_style_registry

NEW = {
    'continue문': 'create_safe_guard_continue',
    '식별 비교': 'create_safe_literal_identity',
    '산술 연산': 'create_safe_arithmetic_expression',
}


def _plan(style=None, target=None):
    return build_transform_plan({
        'missing_syntax_tags': [],
        'missing_concept_tags': [],
        'style_syntax_names': set(),
        'style_concept_names': set(),
        'target_syntax_names': set(),
        'target_concept_names': set(),
        'style_metrics': style or {},
        'target_analysis': {'metrics': target or {}},
    })


class Batch12IntegrationTests(unittest.TestCase):
    def test_three_real_tag_links(self):
        for tag, action in NEW.items():
            with self.subTest(tag=tag):
                self.assertEqual(get_tag_transform_status(tag), 'linked')
                self.assertEqual(get_create_action_for_tag(tag), action)
                self.assertTrue(callable(_get_transform_function(action)))

    def test_unique_registry_75_and_27_compare_only(self):
        tree = ast.parse(Path(mapping.__file__).read_text(encoding='utf-8-sig'))
        d = [node.value for node in tree.body
             if isinstance(node, ast.AnnAssign)
             and isinstance(node.target, ast.Name)
             and node.target.id == 'CREATE_ACTION_BY_TAG']
        self.assertEqual(len(d), 1)
        keys = [node.value for node in d[0].keys]
        # CAPSTONE_UNMAPPED_BATCH13_COMPAT12_V1: retain Batch 12 baseline.
        self.assertGreaterEqual(len(keys), 75)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), set(mapping.CREATE_ACTION_BY_TAG))
        all_tags = set(mapping.SYNTAX_TAG_RULES) | set(mapping.CONCEPT_TAG_RULES)
        self.assertTrue(set(keys) <= all_tags)
        self.assertEqual(mapping.COMPARE_ONLY_TAGS, all_tags - set(keys))
        self.assertEqual(len(keys) + len(mapping.COMPARE_ONLY_TAGS), len(all_tags))

    def test_registry_audit_no_issues(self):
        self.assertEqual(audit_style_registry()['issues'], [])

    def test_metric_based_planning(self):
        cases = (
            ({'continue_count': 1}, {'loop_count': 1, 'if_count': 1},
             'create_safe_guard_continue'),
            ({'identity_compare_count': 2}, {'compare_count': 1, 'none_count': 1},
             'create_safe_literal_identity'),
            ({'bin_op_count': 1}, {'call_count': 1, 'attribute_count': 1,
                                  'import_count': 1}, 'create_safe_arithmetic_expression'),
        )
        for style, target, action in cases:
            with self.subTest(action=action):
                actual = [r['action'] for r in _plan(style, target)['actions']]
                self.assertEqual(actual.count(action), 1)

    def test_no_preference_or_no_target_evidence(self):
        saved = {'continue_count': 2, 'identity_compare_count': 3, 'bin_op_count': 1}
        target = {'loop_count': 1, 'if_count': 2, 'compare_count': 1,
                  'none_count': 1, 'call_count': 1, 'attribute_count': 1,
                  'import_count': 1}
        self.assertFalse(set(NEW.values()) & {
            i['action'] for i in _plan({}, target)['actions']
        })
        self.assertFalse(set(NEW.values()) & {
            i['action'] for i in _plan(saved, {})['actions']
        })
        existing = dict(target, continue_count=2, identity_compare_count=2,
                        bin_op_count=1)
        self.assertFalse(set(NEW.values()) & {
            i['action'] for i in _plan(saved, existing)['actions']
        })

    def test_dispatcher_applies_all_three(self):
        examples = (
            ('continue문', 'for x in [1,2]:\n    if x < 0:\n        pass\n'
             '    else:\n        print(x)\n', 'continue'),
            ('식별 비교', 'x = None\nif x == None:\n    print("yes")\n', 'x is None'),
            ('산술 연산', 'import operator\nx = operator.add(1,2)\n', '1 + 2'),
        )
        for tag, code, marker in examples:
            with self.subTest(tag=tag):
                result, outcome = _apply_style_action(
                    code=code,
                    action_item={'tag': tag, 'action': NEW[tag], 'reason': 'batch12'},
                    applied_rules=[], warnings=[])
                self.assertEqual(outcome['status'], 'applied')
                self.assertIn(marker, result)

    def test_prev_mappings_are_unchanged(self):
        expected = {
            'len 사용': 'create_safe_literal_len',
            'zip 사용': 'create_safe_literal_zip',
            '슬라이싱 사용': 'create_safe_list_slice',
            'enumerate 사용': 'create_safe_enumerate',
            'range 사용': 'create_safe_literal_range',
            '함수 호출 중심 구조': 'create_safe_operator_call',
        }
        for tag, action in expected.items():
            with self.subTest(tag=tag):
                self.assertEqual(get_create_action_for_tag(tag), action)

    def test_unsafe_tags_remain_compare_only(self):
        # CAPSTONE_BATCH23_LEGACY_TEST_FIX_V1
        self.assertEqual(get_tag_transform_status('전역 변수 사용'), 'linked')
        self.assertEqual(get_create_action_for_tag('전역 변수 사용'), 'create_safe_readonly_global')
        # CAPSTONE_BATCH27_LEGACY_FILE_IO_V1: only await remains compare-only.
        self.assertEqual(get_tag_transform_status('파일 입출력 구조'), 'linked')
        for tag in ('await 사용',):
            with self.subTest(tag=tag):
                self.assertEqual(get_tag_transform_status(tag), 'compare_only')


if __name__ == '__main__':
    unittest.main()
