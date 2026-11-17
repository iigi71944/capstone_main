"""Batch 10 wiring regression: preserve earlier actions and add enumerate."""
import unittest
import ast
from pathlib import Path
import app.services.style_tag_transform_map_service as tag_registry

from app.services.style_tag_transform_map_service import (
    get_create_action_for_tag, get_tag_transform_status,
)
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_apply_service import _get_transform_function, _apply_style_action
from app.services.style_transform_audit_service import audit_style_registry


EXPECTED = {
    '복합 할당': 'create_safe_augmented_assignment',
    'enumerate 사용': 'create_safe_enumerate',
    '키워드 인자 사용': 'create_safe_keyword_call',
    '검증 로직 중심 구조': 'create_safe_validation_condition',
    '반환 중심 구조': 'create_safe_multiple_returns',
}


def plan(style_metrics=None, target_metrics=None, missing_concept=()):
    return build_transform_plan({
        'missing_syntax_tags': [],
        'missing_concept_tags': [{'tag': x} for x in missing_concept],
        'style_syntax_names': set(),
        'style_concept_names': set(missing_concept),
        'target_syntax_names': set(),
        'target_concept_names': set(),
        'style_metrics': style_metrics or {},
        'target_analysis': {'metrics': target_metrics or {}},
    })


class Batch10WiringTests(unittest.TestCase):
    def test_existing_four_and_enumerate_linked(self):
        for name, action in EXPECTED.items():
            with self.subTest(tag=name):
                self.assertEqual(get_tag_transform_status(name), 'linked')
                self.assertEqual(get_create_action_for_tag(name), action)
                self.assertIsNotNone(_get_transform_function(action))

    def test_registry_has_unique_tag_keys(self):
        tree = ast.parse(Path(tag_registry.__file__).read_text(encoding='utf-8-sig'))
        mappings = [node.value for node in tree.body if isinstance(node, ast.AnnAssign)
                    and isinstance(node.target, ast.Name) and node.target.id == 'CREATE_ACTION_BY_TAG']
        self.assertEqual(len(mappings), 1)
        keys = [key.value for key in mappings[0].keys if isinstance(key, ast.Constant)
                and isinstance(key.value, str)]
        self.assertEqual(len(keys), len(set(keys)), '중복된 태그 매핑이 발견됐습니다.')

    def test_registry_audit(self):
        self.assertEqual(audit_style_registry()['issues'], [])

    def test_compound_selected_from_saved_metric(self):
        actions = [a['action'] for a in plan({'aug_assign_count': 2}, {'aug_assign_count': 0})['actions']]
        self.assertIn('create_safe_augmented_assignment', actions)

    def test_enumerate_selected_from_saved_metric(self):
        actions = [a['action'] for a in plan({'enumerate_call_count': 2}, {'enumerate_call_count': 0})['actions']]
        self.assertIn('create_safe_enumerate', actions)

    def test_keyword_selected_from_saved_metric(self):
        actions = [a['action'] for a in plan({'keyword_arg_count': 2}, {'keyword_arg_count': 0})['actions']]
        self.assertIn('create_safe_keyword_call', actions)

    def test_all_metric_actions_selected_once(self):
        actions = [a['action'] for a in plan({
            'aug_assign_count': 2, 'enumerate_call_count': 1, 'keyword_arg_count': 1
        }, {'aug_assign_count': 0, 'enumerate_call_count': 0, 'keyword_arg_count': 0})['actions']]
        for action in ('create_safe_augmented_assignment', 'create_safe_enumerate', 'create_safe_keyword_call'):
            self.assertEqual(actions.count(action), 1)

    def test_no_preference_no_invention(self):
        actions = [a['action'] for a in plan({}, {
            'aug_assign_count': 0, 'enumerate_call_count': 0, 'keyword_arg_count': 0
        })['actions']]
        for action in ('create_safe_augmented_assignment', 'create_safe_enumerate', 'create_safe_keyword_call'):
            self.assertNotIn(action, actions)

    def test_target_already_matches_no_redundant_plan(self):
        actions = [a['action'] for a in plan(
            {'aug_assign_count': 1, 'enumerate_call_count': 1, 'keyword_arg_count': 1},
            {'aug_assign_count': 2, 'enumerate_call_count': 2, 'keyword_arg_count': 2}
        )['actions']]
        for action in ('create_safe_augmented_assignment', 'create_safe_enumerate', 'create_safe_keyword_call'):
            self.assertNotIn(action, actions)

    def test_saved_metrics_not_modified(self):
        source = {'aug_assign_count': 1, 'enumerate_call_count': 1}
        target = {'aug_assign_count': 0, 'enumerate_call_count': 0}
        before = source.copy(), target.copy()
        plan(source, target)
        self.assertEqual(before, (source, target))

    def test_validation_concept_trigger(self):
        actions = [a['action'] for a in plan(missing_concept=['검증 로직 중심 구조'])['actions']]
        self.assertIn('create_safe_validation_condition', actions)

    def test_return_concept_trigger(self):
        actions = [a['action'] for a in plan(missing_concept=['반환 중심 구조'])['actions']]
        self.assertIn('create_safe_multiple_returns', actions)

    def test_dispatcher_applies_compound(self):
        source = 'count = 3\ncount = count + 2\nprint(count)\n'
        applied, result = _apply_style_action(
            code=source, action_item={'tag': '복합 할당', 'action': 'create_safe_augassign', 'reason': 'test'},
            applied_rules=[], warnings=[])
        self.assertEqual(result['status'], 'applied')
        self.assertIn('count += 2', applied)

    def test_dispatcher_applies_enumerate(self):
        source = 'items = [1,2]\nfor i in range(len(items)):\n    print(items[i])\n'
        applied, result = _apply_style_action(
            code=source, action_item={'tag': 'enumerate 사용', 'action': 'create_safe_enumerate', 'reason': 'test'},
            applied_rules=[], warnings=[])
        self.assertEqual(result['status'], 'applied')
        self.assertIn('enumerate(items)', applied)

    def test_no_unintended_comparison_only_change(self):
        self.assertEqual(get_tag_transform_status('await 사용'), 'linked')


if __name__ == '__main__':
    unittest.main()
