"""Batch 11 registry, metric preference, and runtime dispatch integration."""
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
    'len 사용': 'create_safe_literal_len',
    'zip 사용': 'create_safe_literal_zip',
    '슬라이싱 사용': 'create_safe_list_slice',
}


def plan(style=None, target=None):
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


class Batch11WiringTests(unittest.TestCase):
    def test_three_genuinely_new_linked_tags(self):
        for name, action in NEW.items():
            with self.subTest(tag=name):
                self.assertEqual(get_tag_transform_status(name), 'linked')
                self.assertEqual(get_create_action_for_tag(name), action)
                self.assertTrue(callable(_get_transform_function(action)))

    def test_unique_registry_preserves_batch11_baseline(self):
        # This is a Batch 11 regression test. Later batches may add links;
        # ensure no existing Batch 11 registration was removed instead of
        # freezing the registry size at 72 indefinitely.
        tree = ast.parse(Path(mapping.__file__).read_text(encoding='utf-8-sig'))
        registers = [node.value for node in tree.body
                     if isinstance(node, ast.AnnAssign)
                     and isinstance(node.target, ast.Name)
                     and node.target.id == 'CREATE_ACTION_BY_TAG']
        self.assertEqual(len(registers), 1)
        keys = [node.value for node in registers[0].keys]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertGreaterEqual(len(keys), 72)
        self.assertEqual(set(keys), set(mapping.CREATE_ACTION_BY_TAG))
        all_tags = set(mapping.SYNTAX_TAG_RULES) | set(mapping.CONCEPT_TAG_RULES)
        self.assertTrue(set(keys) <= all_tags)
        self.assertEqual(mapping.COMPARE_ONLY_TAGS, all_tags - set(keys))
        self.assertEqual(len(keys) + len(mapping.COMPARE_ONLY_TAGS), len(all_tags))

    def test_registry_audit_ok(self):
        self.assertEqual(audit_style_registry()['issues'], [])

    def test_saved_metrics_select_real_target_patterns(self):
        cases = (
            ({'len_call_count': 2}, {'sum_call_count': 1}, 'create_safe_literal_len'),
            ({'zip_call_count': 1}, {'loop_count': 1}, 'create_safe_literal_zip'),
            ({'slicing_count': 3}, {'list_method_call_count': 1}, 'create_safe_list_slice'),
        )
        for saved, target, action in cases:
            with self.subTest(action=action):
                items = [item['action'] for item in plan(saved, target)['actions']]
                self.assertEqual(items.count(action), 1)

    def test_all_three_distinct_plan_actions(self):
        saved = {'len_call_count': 2, 'zip_call_count': 1, 'slicing_count': 3}
        target = {'sum_call_count': 1, 'loop_count': 1, 'list_method_call_count': 2}
        items = [item['action'] for item in plan(saved, target)['actions']]
        for action in NEW.values():
            self.assertEqual(items.count(action), 1)

    def test_no_saved_preference_or_no_target_evidence(self):
        for saved, target in (({}, {'sum_call_count': 1, 'loop_count': 1,
                                     'list_method_call_count': 1}),
                              ({'len_call_count': 1, 'zip_call_count': 1,
                                'slicing_count': 1}, {})):
            items = [item['action'] for item in plan(saved, target)['actions']]
            self.assertFalse(set(items) & set(NEW.values()))

    def test_target_already_has_preference(self):
        saved = {'len_call_count': 1, 'zip_call_count': 1, 'slicing_count': 1}
        target = {'len_call_count': 2, 'zip_call_count': 2, 'slicing_count': 2,
                  'sum_call_count': 1, 'loop_count': 1, 'list_method_call_count': 1}
        items = [item['action'] for item in plan(saved, target)['actions']]
        self.assertFalse(set(items) & set(NEW.values()))

    def test_action_dispatcher_really_changes_code(self):
        examples = (
            ('len 사용', 'result = sum(1 for x in [1,2])\nprint(result)\n', 'len('),
            ('zip 사용', 'for a,b in [(1,2),(3,4)]:\n    print(a+b)\n', 'zip('),
            ('슬라이싱 사용', 'xs = [1,2]\ny = xs.copy()\nprint(y)\n', 'xs[:]'),
        )
        for tag, source, marker in examples:
            with self.subTest(tag=tag):
                changed, result = _apply_style_action(
                    code=source,
                    action_item={'tag': tag, 'action': NEW[tag], 'reason': 'batch11'},
                    applied_rules=[], warnings=[])
                self.assertEqual(result['status'], 'applied')
                self.assertIn(marker, changed)

    def test_previous_action_mappings_still_intact(self):
        previous = {
            '복합 할당': 'create_safe_augmented_assignment',
            '키워드 인자 사용': 'create_safe_keyword_call',
            '검증 로직 중심 구조': 'create_safe_validation_condition',
            '반환 중심 구조': 'create_safe_multiple_returns',
            'enumerate 사용': 'create_safe_enumerate',
        }
        for tag, action in previous.items():
            with self.subTest(tag=tag):
                self.assertEqual(get_create_action_for_tag(tag), action)

    def test_unsupported_await_remains_compare_only(self):
        self.assertEqual(get_tag_transform_status('await 사용'), 'compare_only')


if __name__ == '__main__':
    unittest.main()
