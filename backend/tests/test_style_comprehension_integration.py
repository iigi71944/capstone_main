"""Regression tests for saved-style list/comprehension action integration.

Run from capstone_main/backend with:
python -m unittest discover -s tests -p 'test_style_comprehension_integration.py' -v
"""

import ast
import unittest
from unittest.mock import patch

from app.services.improvement.safe_list_comprehension_service import (
    transform_for_append_to_list_comprehension,
    transform_list_comprehension_to_for_append,
)
from app.services.style_apply_service import _get_transform_function, apply_coding_style
from app.services.style_tag_transform_map_service import get_create_action_for_tag
from app.services.style_transform_plan_service import build_transform_plan


def make_diff(*, missing_syntax=(), missing_concept=(),
              style_syntax=(), style_concept=(), target_syntax=(),
              target_concept=(), style_metrics=None, target_metrics=None):
    return {
        'missing_syntax_tags': [{'tag': tag} for tag in missing_syntax],
        'missing_concept_tags': [{'tag': tag} for tag in missing_concept],
        'style_syntax_names': set(style_syntax),
        'style_concept_names': set(style_concept),
        'target_syntax_names': set(target_syntax),
        'target_concept_names': set(target_concept),
        'style_metrics': style_metrics or {},
        'target_analysis': {'metrics': target_metrics or {}},
    }


class StyleListIntegrationTests(unittest.TestCase):
    def test_specific_comprehension_tag_uses_safe_action(self):
        self.assertEqual(get_create_action_for_tag('리스트 컴프리헨션'),
                         'create_comprehension_collection')
        self.assertIs(_get_transform_function('create_safe_comprehension_collection'),
                      transform_for_append_to_list_comprehension)

    def test_specific_append_tag_uses_safe_action(self):
        self.assertEqual(get_create_action_for_tag('리스트 누적 방식 사용'),
                         'create_append_collection')
        self.assertIs(_get_transform_function('create_safe_append_collection'),
                      transform_list_comprehension_to_for_append)

    def test_public_tag_mapping_stays_backward_compatible(self):
        expected = {
            '리스트 누적 방식 사용': 'create_append_collection',
            '리스트 메서드 호출': 'create_append_collection',
            '리스트 컴프리헨션': 'create_comprehension_collection',
            '컴프리헨션 기반 간결 구조': 'create_comprehension_collection',
        }
        for tag, action in expected.items():
            with self.subTest(tag=tag):
                self.assertEqual(get_create_action_for_tag(tag), action)

    def test_other_collection_actions_remain_connected(self):
        for action in ('create_append_collection', 'create_comprehension_collection',
                       'create_collection_style'):
            self.assertIsNotNone(_get_transform_function(action))

    def test_all_previous_non_collection_actions_remain_connected(self):
        for action in ('create_direct_iteration', 'create_index_iteration',
                       'create_while_iteration', 'create_counted_while_to_for',
                       'create_if_statement', 'create_conditional_expression',
                       'create_return_structure', 'create_sum_aggregation',
                       'create_fstring_style', 'create_sort_style'):
            self.assertIsNotNone(_get_transform_function(action))

    def test_plan_for_list_comprehension(self):
        diff = make_diff(missing_syntax=['리스트 컴프리헨션'])
        actions = build_transform_plan(diff)['actions']
        self.assertEqual([a['action'] for a in actions],
                         ['create_safe_comprehension_collection'])

    def test_plan_for_append_style(self):
        diff = make_diff(missing_concept=['리스트 누적 방식 사용'])
        actions = build_transform_plan(diff)['actions']
        self.assertEqual([a['action'] for a in actions],
                         ['create_safe_append_collection'])

    def test_comprehension_specific_action_preempts_broad_action(self):
        diff = make_diff(missing_syntax=['리스트 컴프리헨션'],
                         missing_concept=['컴프리헨션 기반 간결 구조'])
        actions = build_transform_plan(diff)['actions']
        self.assertEqual([a['action'] for a in actions],
                         ['create_safe_comprehension_collection'])

    def test_append_specific_action_preempts_broad_method(self):
        diff = make_diff(missing_syntax=['리스트 메서드 호출'],
                         missing_concept=['리스트 누적 방식 사용'])
        actions = build_transform_plan(diff)['actions']
        self.assertEqual([a['action'] for a in actions],
                         ['create_safe_append_collection'])

    def test_broad_action_without_specific_tag_remains(self):
        diff = make_diff(missing_concept=['컴프리헨션 기반 간결 구조'])
        self.assertEqual([a['action'] for a in build_transform_plan(diff)['actions']],
                         ['create_comprehension_collection'])

    def test_filtered_preference_uses_safe_function_and_no_duplicate(self):
        diff = make_diff(
            missing_syntax=['리스트 컴프리헨션'],
            missing_concept=['컴프리헨션 기반 간결 구조'],
            style_syntax=['리스트 컴프리헨션'],
            style_concept=['데이터 필터링 구조', '컴프리헨션 기반 간결 구조'],
            target_syntax=['for문'],
            target_concept=['데이터 필터링 구조'],
            target_metrics={'append_call_count': 1, 'filter_pattern_count': 1},
        )
        actions = build_transform_plan(diff)['actions']
        self.assertEqual([a['action'] for a in actions],
                         ['create_safe_comprehension_collection'])

    def test_non_comp_filter_action_not_changed(self):
        diff = make_diff(missing_concept=['데이터 필터링 구조'])
        self.assertEqual([a['action'] for a in build_transform_plan(diff)['actions']],
                         ['create_filter_style'])

    def test_independent_filter_action_stays_available(self):
        diff = make_diff(missing_syntax=['리스트 컴프리헨션'],
                         missing_concept=['데이터 필터링 구조'])
        actions = [a['action'] for a in build_transform_plan(diff)['actions']]
        self.assertIn('create_safe_comprehension_collection', actions)
        self.assertIn('create_filter_style', actions)

    def test_conflicting_style_directions_fail_closed(self):
        diff = make_diff(missing_syntax=['리스트 컴프리헨션', '리스트 메서드 호출'],
                         missing_concept=['리스트 누적 방식 사용'])
        actions = build_transform_plan(diff)['actions']
        self.assertFalse([a for a in actions if 'collection' in a['action']])

    def test_unrelated_plan_action_is_not_removed(self):
        diff = make_diff(missing_syntax=['리스트 컴프리헨션', '삼항 조건식'])
        actions = [a['action'] for a in build_transform_plan(diff)['actions']]
        self.assertIn('create_conditional_expression', actions)
        self.assertIn('create_safe_comprehension_collection', actions)

    def _run_style(self, source, diff):
        # Keep actual plan/dispatcher and transformation code; isolate the
        # diff checker and execution verifier from unrelated project services.
        with patch('app.services.style_apply_service.compare_style_with_target_code', return_value=diff), \
             patch('app.services.style_apply_service.compare_after_transform', return_value={
                 'missing_syntax_tags': [], 'missing_concept_tags': []}), \
             patch('app.services.style_apply_service.verify_execution_equivalence',
                   return_value={'status': 'equivalent', 'equivalent': True,
                                 'message': '', 'function_verification': None}):
            return apply_coding_style(source, {'syntax_tags': [], 'concept_tags': []})

    def test_end_to_end_comprehension_saved_style(self):
        before = 'result = []\nfor x in [1, 2, 3]:\n    result.append(x * 2)\nprint(result)\n'
        diff = make_diff(missing_syntax=['리스트 컴프리헨션'])
        result = self._run_style(before, diff)
        self.assertEqual(len(result), 6)
        ast.parse(result[0])
        self.assertIn('result = [x * 2 for x in [1, 2, 3]]', result[0])
        self.assertEqual(result[3], [])
        scope_a, scope_b = {}, {}
        exec(before, scope_a)
        exec(result[0], scope_b)
        self.assertEqual(scope_a['result'], scope_b['result'])

    def test_end_to_end_append_saved_style(self):
        before = 'result = [x * 2 for x in [1, 2, 3]]\nprint(result)\n'
        diff = make_diff(missing_syntax=['리스트 메서드 호출'],
                         missing_concept=['리스트 누적 방식 사용'])
        result = self._run_style(before, diff)
        self.assertEqual(len(result), 6)
        ast.parse(result[0])
        self.assertIn('.append(', result[0])
        self.assertIn('try:', result[0])
        self.assertEqual(result[3], [])
        scope_a, scope_b = {}, {}
        exec(before, scope_a)
        exec(result[0], scope_b)
        self.assertEqual(scope_a['result'], scope_b['result'])

    def test_end_to_end_rejects_unsafe_and_untouched_code(self):
        before = 'result = []\nfor x in [1, 2]:\n    result.append(f(x))\n'
        diff = make_diff(missing_syntax=['리스트 컴프리헨션'])
        result = self._run_style(before, diff)
        self.assertEqual(result[0], before)
        self.assertTrue(any('안전하게 변환할 수 있는' in message for message in result[3]))

    def test_end_to_end_conditioned_loop(self):
        before = 'result = []\nfor x in [1, 2, 3]:\n    if x > 1:\n        result.append(x * 2)\n'
        diff = make_diff(
            missing_syntax=['리스트 컴프리헨션'],
            style_syntax=['리스트 컴프리헨션'],
            style_concept=['데이터 필터링 구조'],
            target_syntax=['for문'],
            target_concept=['데이터 필터링 구조'],
            target_metrics={'append_call_count': 1, 'filter_pattern_count': 1})
        result = self._run_style(before, diff)
        self.assertIn('if x > 1]', result[0])
        self.assertEqual(result[3], [])


if __name__ == '__main__':
    unittest.main()
