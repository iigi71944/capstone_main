"""Batch 30 follow-up: keep implicit/default-syntax preference signals separate.

Without this guard, a style with sorted(..., reverse=False) and .strip(None)
accidentally also requests unrelated generic keyword/bool/None conversions.
These tests intentionally run the REAL style plan, not a reduced stub.
"""
from __future__ import annotations

import ast
import unittest

from app.services.metric_service import calculate_metrics
from app.services.style_transform_plan_service import (
    _generic_preference_metric_count,
    build_transform_plan,
)


def _metrics(src: str) -> dict:
    return calculate_metrics(ast.parse(src))


def _actions(saved: str, target: str) -> set[str]:
    plan = build_transform_plan({
        'style_metrics': _metrics(saved),
        'target_analysis': {'metrics': _metrics(target)},
        'style_syntax_names': set(),
        'style_concept_names': set(),
        'target_syntax_names': set(),
        'target_concept_names': set(),
        'missing_syntax_tags': [],
        'missing_concept_tags': [],
    })
    return {row['action'] for row in plan['actions']}


class DefaultArgumentMetricIndependenceTests(unittest.TestCase):
    def test_01_sort_explicit_keeps_only_intended_fine_style(self):
        actions = _actions('a = sorted([3, 1], reverse=False)\n',
                           'a = sorted([3, 1])\n')
        self.assertIn('create_safe_explicit_sorted_reverse', actions)
        self.assertNotIn('create_safe_keyword_call', actions)
        self.assertNotIn('create_safe_boolean_literal', actions)

    def test_02_sort_implicit_no_false_positional_preference(self):
        actions = _actions('a = sorted([3, 1])\n',
                           'a = sorted([3, 1], reverse=False)\n')
        self.assertIn('create_safe_implicit_sorted_reverse', actions)
        self.assertNotIn('create_safe_positional_call', actions)

    def test_03_strip_none_no_false_none_preference(self):
        actions = _actions('name = " hi ".strip(None)\n',
                           'data = {}\nname = " hi ".strip()\n')
        self.assertIn('create_safe_explicit_strip_default', actions)
        self.assertNotIn('create_safe_empty_dict_none', actions)

    def test_04_combined_fine_patterns_do_not_trigger_generic_rules(self):
        actions = _actions('a = sorted([3, 1], reverse=False)\n'
                           'b = " hi ".strip(None)\n',
                           'a = sorted([3, 1])\n'
                           'b = " hi ".strip()\n')
        self.assertEqual(actions, {
            'create_safe_explicit_sorted_reverse',
            'create_safe_explicit_strip_default',
        })

    def test_05_reverse_combination_no_false_positional_preference(self):
        actions = _actions('a = sorted([3, 1])\n'
                           'b = " hi ".strip()\n',
                           'a = sorted([3, 1], reverse=False)\n'
                           'b = " hi ".strip(None)\n')
        self.assertIn('create_safe_implicit_sorted_reverse', actions)
        self.assertIn('create_safe_implicit_strip_default', actions)
        self.assertNotIn('create_safe_positional_call', actions)

    def test_06_other_keyword_argument_still_counts(self):
        actions = _actions('a = sorted([3, 1], reverse=False)\n'
                           'print("hi", end="")\n',
                           'a = sorted([3, 1])\n')
        self.assertIn('create_safe_keyword_call', actions)

    def test_07_other_boolean_literal_still_counts(self):
        actions = _actions('a = sorted([3, 1], reverse=False)\nflag = True\n',
                           'a = sorted([3, 1])\n')
        self.assertIn('create_safe_boolean_literal', actions)

    def test_08_other_none_literal_still_counts(self):
        actions = _actions('name = " hi ".strip(None)\nmissing = None\n',
                           'data = {}\nname = " hi ".strip()\n')
        self.assertIn('create_safe_empty_dict_none', actions)

    def test_09_old_style_metrics_keep_old_meaning(self):
        original = {
            'keyword_arg_count': 2, 'positional_arg_count': 3,
            'boolean_literal_count': 1, 'none_count': 1,
        }
        for key in original:
            self.assertEqual(_generic_preference_metric_count(original, key),
                             original[key])

    def test_10_numeric_safe_subtraction_and_bad_types(self):
        data = {'keyword_arg_count': 1, 'boolean_literal_count': 1,
                'positional_arg_count': 2, 'none_count': 1,
                'sorted_reverse_false_explicit_count': 4,
                'strip_none_explicit_count': 3}
        for key in ('keyword_arg_count', 'boolean_literal_count',
                    'positional_arg_count', 'none_count'):
            self.assertEqual(_generic_preference_metric_count(data, key), 0)
        self.assertEqual(_generic_preference_metric_count(
            {'keyword_arg_count': True, 'sorted_reverse_false_explicit_count': 2},
            'keyword_arg_count'), 0)

    def test_11_unrelated_metric_is_unchanged(self):
        data = {'call_count': 5, 'sorted_reverse_false_explicit_count': 3}
        self.assertEqual(_generic_preference_metric_count(data, 'call_count'), 5)

    def test_12_fine_counter_is_not_ignored(self):
        data = {'sorted_reverse_false_explicit_count': 3,
                'strip_none_explicit_count': 2}
        self.assertEqual(_generic_preference_metric_count(
            data, 'sorted_reverse_false_explicit_count'), 3)
        self.assertEqual(_generic_preference_metric_count(
            data, 'strip_none_explicit_count'), 2)


if __name__ == '__main__':
    unittest.main()
