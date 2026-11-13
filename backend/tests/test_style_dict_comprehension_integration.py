"""Regression tests for safe dictionary conversion in saved-style application.

Run from capstone_main/backend:
    python -m unittest discover -s tests -p 'test_style_dict_comprehension_integration.py' -v
"""

import ast
import contextlib
import io
import unittest
from unittest.mock import patch

from app.services.improvement.safe_dict_comprehension_service import (
    transform_dict_comprehension_to_for_assignment,
    transform_for_assignment_to_dict_comprehension,
)
from app.services.style_apply_service import _get_transform_function, apply_coding_style
from app.services.style_tag_transform_map_service import get_create_action_for_tag
from app.services.style_transform_plan_service import build_transform_plan


def diff(*, missing_syntax=(), missing_concept=(), style_syntax=(), style_concept=(),
         target_syntax=(), target_concept=(), target_metrics=None):
    return {
        'missing_syntax_tags': [{'tag': x} for x in missing_syntax],
        'missing_concept_tags': [{'tag': x} for x in missing_concept],
        'style_syntax_names': set(style_syntax),
        'style_concept_names': set(style_concept),
        'target_syntax_names': set(target_syntax),
        'target_concept_names': set(target_concept),
        'style_metrics': {},
        'target_analysis': {'metrics': target_metrics or {}},
    }


def actions(d):
    return [i['action'] for i in build_transform_plan(d)['actions']]


def observe(code):
    ns = {}
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(code, '<dict-style-integration>', 'exec'), ns)
    return output.getvalue(), ns.get('result')


def apply_with_diff(source, d, validation=None):
    if validation is None:
        validation = {'status': 'equivalent', 'equivalent': True, 'message': '',
                      'function_verification': None}
    with patch('app.services.style_apply_service.compare_style_with_target_code', return_value=d), \
         patch('app.services.style_apply_service.compare_after_transform', return_value={
             'missing_syntax_tags': [], 'missing_concept_tags': []}), \
         patch('app.services.style_apply_service.verify_execution_equivalence', return_value=validation):
        return apply_coding_style(source, {'syntax_tags': [], 'concept_tags': []})


class DictIntegrationTests(unittest.TestCase):
    def test_public_forward_mapping_unchanged(self):
        self.assertEqual(get_create_action_for_tag('딕셔너리 컴프리헨션'),
                         'create_dict_comprehension')

    def test_public_mapping_concept_unchanged(self):
        self.assertEqual(get_create_action_for_tag('딕셔너리 기반 매핑 구조'),
                         'create_mapping_style')

    def test_new_forward_dispatch(self):
        self.assertIs(_get_transform_function('create_safe_dict_comprehension'),
                      transform_for_assignment_to_dict_comprehension)

    def test_new_reverse_dispatch(self):
        self.assertIs(_get_transform_function('create_safe_dict_loop'),
                      transform_dict_comprehension_to_for_assignment)

    def test_legacy_dispatch_stays(self):
        self.assertIsNotNone(_get_transform_function('create_dict_comprehension'))
        self.assertIsNotNone(_get_transform_function('create_mapping_style'))

    def test_forward_plan(self):
        self.assertEqual(actions(diff(missing_syntax=['딕셔너리 컴프리헨션'])),
                         ['create_safe_dict_comprehension'])

    def test_reverse_plan_from_literal_and_loop(self):
        self.assertEqual(actions(diff(style_syntax=['for문', '딕셔너리 리터럴'],
                                      target_syntax=['딕셔너리 컴프리헨션'])),
                         ['create_safe_dict_loop'])

    def test_reverse_plan_from_mapping_concept(self):
        self.assertEqual(actions(diff(style_syntax=['for문'],
                                      style_concept=['딕셔너리 기반 매핑 구조'],
                                      target_syntax=['딕셔너리 컴프리헨션'])),
                         ['create_safe_dict_loop'])

    def test_do_not_infer_reverse_from_unrelated_for(self):
        self.assertNotIn('create_safe_dict_loop', actions(diff(
            style_syntax=['for문'], target_syntax=['딕셔너리 컴프리헨션'])))

    def test_do_not_infer_reverse_from_unrelated_dict(self):
        self.assertNotIn('create_safe_dict_loop', actions(diff(
            style_syntax=['딕셔너리 리터럴'], target_syntax=['딕셔너리 컴프리헨션'])))

    def test_do_not_reverse_when_style_already_has_comprehension(self):
        self.assertNotIn('create_safe_dict_loop', actions(diff(
            style_syntax=['for문', '딕셔너리 컴프리헨션', '딕셔너리 리터럴'],
            target_syntax=['딕셔너리 컴프리헨션'])))

    def test_reverse_preempts_legacy_mapping_for_same_tag(self):
        self.assertEqual(actions(diff(
            style_syntax=['for문', '딕셔너리 리터럴'],
            style_concept=['딕셔너리 기반 매핑 구조'],
            target_syntax=['딕셔너리 컴프리헨션'],
            missing_concept=['딕셔너리 기반 매핑 구조'])),
            ['create_safe_dict_loop'])

    def test_forward_specific_action_preempts_broad_mapping(self):
        self.assertEqual(actions(diff(
            missing_syntax=['딕셔너리 컴프리헨션'],
            missing_concept=['딕셔너리 기반 매핑 구조'])),
            ['create_safe_dict_comprehension'])

    def test_unrelated_legacy_mapping_remains_without_safe_action(self):
        self.assertEqual(actions(diff(
            missing_concept=['딕셔너리 기반 매핑 구조'])),
            ['create_mapping_style'])

    def test_no_duplicate_when_both_dict_actions_proposed(self):
        self.assertEqual(actions(diff(
            style_syntax=['for문', '딕셔너리 리터럴'],
            target_syntax=['딕셔너리 컴프리헨션'],
            missing_syntax=['딕셔너리 컴프리헨션'])), [])

    def test_forward_and_list_unchanged(self):
        expected = actions(diff(missing_syntax=['딕셔너리 컴프리헨션', '리스트 컴프리헨션']))
        self.assertIn('create_safe_dict_comprehension', expected)
        self.assertIn('create_safe_comprehension_collection', expected)
        self.assertEqual(len(expected), 2)

    def test_dict_and_condition_unrelated(self):
        values = actions(diff(missing_syntax=['딕셔너리 컴프리헨션', '삼항 조건식']))
        self.assertIn('create_conditional_expression', values)
        self.assertIn('create_safe_dict_comprehension', values)

    def test_existing_non_dict_actions_unchanged(self):
        for name in ('create_direct_iteration', 'create_while_iteration',
                     'create_safe_append_collection', 'create_safe_comprehension_collection',
                     'create_if_statement', 'create_sort_style'):
            with self.subTest(action=name):
                self.assertIsNotNone(_get_transform_function(name))

    def test_forward_end_to_end(self):
        code = 'result = {}\nfor x in [1, 2, 3]:\n    result[x] = x * 2\nprint(result)\n'
        output = apply_with_diff(code, diff(missing_syntax=['딕셔너리 컴프리헨션']))
        self.assertEqual(len(output), 6)
        ast.parse(output[0])
        self.assertIn('result = {x: x * 2 for x in [1, 2, 3]}', output[0])
        self.assertEqual(observe(code), observe(output[0]))
        self.assertEqual(output[3], [])

    def test_filtered_forward_end_to_end(self):
        code = ('result = {}\nfor x in [1, 2, 3]:\n'
                '    if x > 1:\n        result[x] = x * x\nprint(result)\n')
        output = apply_with_diff(code, diff(missing_syntax=['딕셔너리 컴프리헨션']))
        self.assertIn('if x > 1', output[0])
        self.assertEqual(observe(code), observe(output[0]))

    def test_reverse_end_to_end(self):
        code = 'result = {x: x * 2 for x in [1, 2, 3]}\nprint(result)\n'
        output = apply_with_diff(code, diff(
            style_syntax=['for문', '딕셔너리 리터럴'],
            target_syntax=['딕셔너리 컴프리헨션']))
        ast.parse(output[0])
        self.assertIn('for ', output[0])
        self.assertIn('try:', output[0])
        self.assertEqual(observe(code), observe(output[0]))
        self.assertEqual(output[3], [])

    def test_unsafe_forward_is_not_applied(self):
        code = 'result = {}\nfor x in [1, 2]:\n    result[x] = f(x)\n'
        output = apply_with_diff(code, diff(missing_syntax=['딕셔너리 컴프리헨션']))
        self.assertEqual(output[0], code)
        self.assertTrue(any('안전하게 변환할 수 있는' in x for x in output[3]))

    def test_unsafe_reverse_is_not_applied(self):
        code = 'result = {x: f(x) for x in [1, 2]}\n'
        output = apply_with_diff(code, diff(
            style_syntax=['for문', '딕셔너리 리터럴'],
            target_syntax=['딕셔너리 컴프리헨션']))
        self.assertEqual(output[0], code)

    def test_runtime_difference_rolls_back(self):
        code = 'result = {}\nfor x in [1, 2]:\n    result[x] = x\n'
        output = apply_with_diff(code, diff(missing_syntax=['딕셔너리 컴프리헨션']),
            validation={'status': 'different', 'equivalent': False, 'message': 'different'})
        self.assertEqual(output[0], code)
        self.assertEqual(output[2], [])
        self.assertTrue(any('취소' in x for x in output[3]))

    def test_no_change_no_execution_validation(self):
        code = 'result = {1: 2}\n'
        output = apply_with_diff(code, diff(missing_syntax=['딕셔너리 컴프리헨션']))
        self.assertEqual(output[0], code)
        self.assertIsNone(output[5])

    def test_comment_preservation(self):
        code = '# before\nresult = {}\nfor x in [1, 2]:\n    result[x] = x\n# after\n'
        out = apply_with_diff(code, diff(missing_syntax=['딕셔너리 컴프리헨션']))
        self.assertIn('# before', out[0])
        self.assertIn('# after', out[0])


if __name__ == '__main__':
    unittest.main()
