"""Batch29: granular metrics, saved-style plan gates and equivalent edits."""
from __future__ import annotations

import ast
import subprocess
import sys
import unittest

from app.services.metric_service import calculate_metrics
from app.services.improvement.safe_batch29_service import (
    transform_sorted_explicit_reverse_default as sort_exp,
    transform_sorted_implicit_reverse_default as sort_imp,
    transform_strip_explicit_none_default as strip_exp,
    transform_strip_implicit_none_default as strip_imp,
)
from app.services.style_apply_service import _get_transform_function
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_tag_action_policy_service import get_tag_action_policy


def run_code(src):
    result = subprocess.run([sys.executable, '-I', '-c', src],
                            capture_output=True, text=True, timeout=4)
    return result.returncode, result.stdout, result.stderr


def metrics(src):
    return calculate_metrics(ast.parse(src))


def build(saved, target):
    return build_transform_plan({
        'style_metrics': saved,
        'target_analysis': {'metrics': target},
        'style_syntax_names': set(), 'target_syntax_names': set(),
        'style_concept_names': set(), 'target_concept_names': set(),
        'missing_syntax_tags': [], 'missing_concept_tags': [],
    })


class SortedExplicitTriplets(unittest.TestCase):
    def test_basic(self):
        src = 'out = sorted([3, 1, 2])\nprint(out)\n'
        expected = 'out = sorted([3, 1, 2], reverse=False)\nprint(out)\n'
        self.assertEqual(sort_exp(src), expected)
        self.assertEqual(run_code(src), run_code(expected))

    def test_additional(self):
        src = 'out = sorted(["다", "가", "나"])\nprint(out)\n'
        target = sort_exp(src)
        self.assertIn('reverse=False', target)
        self.assertEqual(run_code(src), run_code(target))

    def test_complex(self):
        src = 'a = sorted([5, 4, 2])\nb = sorted([9, 7, 8])\nprint(a, b)\n'
        target = sort_exp(src)
        self.assertEqual(target.count('reverse=False'), 2)
        self.assertEqual(run_code(src), run_code(target))


class SortedImplicitTriplets(unittest.TestCase):
    def test_basic(self):
        src = 'out = sorted([3, 1, 2], reverse=False)\nprint(out)\n'
        expected = 'out = sorted([3, 1, 2])\nprint(out)\n'
        self.assertEqual(sort_imp(src), expected)
        self.assertEqual(run_code(src), run_code(expected))

    def test_additional(self):
        src = 'out = sorted(["서울", "광주"], reverse=False)\nprint(out)\n'
        target = sort_imp(src)
        self.assertNotIn('reverse=False', target)
        self.assertEqual(run_code(src), run_code(target))

    def test_complex(self):
        src = 'a = sorted([2, 1], reverse=False)\nb = sorted([5, 3], reverse=False)\nprint(a, b)\n'
        target = sort_imp(src)
        self.assertEqual(target.count('reverse=False'), 0)
        self.assertEqual(run_code(src), run_code(target))


class StripExplicitTriplets(unittest.TestCase):
    def test_basic(self):
        src = 'value = " hello ".strip()\nprint(value)\n'
        expected = 'value = " hello ".strip(None)\nprint(value)\n'
        self.assertEqual(strip_exp(src), expected)
        self.assertEqual(run_code(src), run_code(expected))

    def test_additional(self):
        src = "value = '  서울  '.strip()\nprint(value)\n"
        target = strip_exp(src)
        self.assertIn('strip(None)', target)
        self.assertEqual(run_code(src), run_code(target))

    def test_complex(self):
        src = 'a = " a ".strip()\nb = " b ".strip()\nprint(a, b)\n'
        target = strip_exp(src)
        self.assertEqual(target.count('strip(None)'), 2)
        self.assertEqual(run_code(src), run_code(target))


class StripImplicitTriplets(unittest.TestCase):
    def test_basic(self):
        src = 'value = " hello ".strip(None)\nprint(value)\n'
        expected = 'value = " hello ".strip()\nprint(value)\n'
        self.assertEqual(strip_imp(src), expected)
        self.assertEqual(run_code(src), run_code(expected))

    def test_additional(self):
        src = "value = '  서울  '.strip(None)\nprint(value)\n"
        target = strip_imp(src)
        self.assertNotIn('strip(None)', target)
        self.assertEqual(run_code(src), run_code(target))

    def test_complex(self):
        src = 'a = " a ".strip(None)\nb = " b ".strip(None)\nprint(a, b)\n'
        target = strip_imp(src)
        self.assertEqual(target.count('strip(None)'), 0)
        self.assertEqual(run_code(src), run_code(target))


class FineMetricTests(unittest.TestCase):
    def test_sorted_default_counts(self):
        m = metrics('a = sorted([3, 1])\nb = sorted([2, 1], reverse=False)\n')
        self.assertEqual(m['sorted_reverse_false_implicit_count'], 1)
        self.assertEqual(m['sorted_reverse_false_explicit_count'], 1)
        self.assertEqual(m['sorted_call_count'], 2)

    def test_sort_true_not_misclassified(self):
        m = metrics('a = sorted([3, 1], reverse=True)\n')
        self.assertEqual(m['sorted_reverse_false_explicit_count'], 0)
        self.assertEqual(m['sorted_reverse_false_implicit_count'], 0)

    def test_literal_string_methods(self):
        m = metrics('a = " hi ".strip()\nb = " x ".strip(None)\n'
                    'c = "ab".split("b")\nd = "ab".replace("a", "x")\n')
        for key, value in {
            'string_strip_call_count': 2, 'strip_none_implicit_count': 1,
            'strip_none_explicit_count': 1, 'string_split_call_count': 1,
            'string_replace_call_count': 1,
        }.items():
            self.assertEqual(m[key], value, key)

    def test_list_methods_granular(self):
        m = metrics('data = []\ndata.extend([1, 2])\ndata.pop()\n')
        self.assertEqual(m['list_extend_call_count'], 1)
        self.assertEqual(m['list_pop_call_count'], 1)
        self.assertEqual(m['list_method_call_count'], 2)

    def test_dict_pop_not_list_pop(self):
        m = metrics('data = {}\ndata.pop("a", None)\n')
        self.assertEqual(m['list_pop_call_count'], 0)

    def test_non_string_strip_not_counted(self):
        m = metrics('def f(x):\n    return x.strip()\n')
        self.assertEqual(m['string_strip_call_count'], 0)

    def test_old_metrics_still_present(self):
        m = metrics('x = [1, 2]\n')
        self.assertIn('function_count', m)
        self.assertIn('list_literal_count', m)
        self.assertIn('aggregation_pattern_count', m)

    def test_style_diff_carries_fine_metrics(self):
        from app.services.style_diff_service import compare_style_with_target_code
        source = 'out = sorted([3, 1], reverse=False)\n'
        target = 'out = sorted([3, 1])\n'
        style = {'syntax_tags': [], 'concept_tags': [], 'metrics': metrics(source)}
        diff = compare_style_with_target_code(style, target)
        self.assertEqual(diff['style_metrics']['sorted_reverse_false_explicit_count'], 1)
        self.assertEqual(diff['target_analysis']['metrics']['sorted_reverse_false_implicit_count'], 1)

    def test_new_metrics_do_not_replace_old_tags(self):
        from app.services.style_diff_service import analyze_code_style
        data = analyze_code_style('out = "  text  ".strip(None)\n')
        self.assertIn('syntax_tags', data)
        self.assertIn('concept_tags', data)
        self.assertIn('string_method_call_count', data['metrics'])
        self.assertEqual(data['metrics']['strip_none_explicit_count'], 1)

    def test_new_metrics_use_nonnegative_integers(self):
        m = metrics('pass\n')
        keys = ('list_extend_call_count','list_pop_call_count','string_strip_call_count',
                'string_split_call_count','string_replace_call_count',
                'sorted_reverse_false_explicit_count','sorted_reverse_false_implicit_count',
                'strip_none_explicit_count','strip_none_implicit_count')
        self.assertTrue(all(type(m[k]) is int and m[k] == 0 for k in keys))


class FineStylePlanTests(unittest.TestCase):
    def test_sorted_explicit_only_on_saved_preference(self):
        saved = metrics('out = sorted([3, 1], reverse=False)\n')
        target = metrics('out = sorted([3, 1])\n')
        actions = [a['action'] for a in build(saved, target)['actions']]
        self.assertIn('create_safe_explicit_sorted_reverse', actions)
        self.assertNotIn('create_safe_implicit_sorted_reverse', actions)

    def test_sorted_implicit_only_on_saved_preference(self):
        saved = metrics('out = sorted([3, 1])\n')
        target = metrics('out = sorted([3, 1], reverse=False)\n')
        actions = [a['action'] for a in build(saved, target)['actions']]
        self.assertIn('create_safe_implicit_sorted_reverse', actions)

    def test_strip_explicit_only_on_saved_preference(self):
        saved = metrics('out = " hi ".strip(None)\n')
        target = metrics('out = " hi ".strip()\n')
        actions = [a['action'] for a in build(saved, target)['actions']]
        self.assertIn('create_safe_explicit_strip_default', actions)

    def test_strip_implicit_only_on_saved_preference(self):
        saved = metrics('out = " hi ".strip()\n')
        target = metrics('out = " hi ".strip(None)\n')
        actions = [a['action'] for a in build(saved, target)['actions']]
        self.assertIn('create_safe_implicit_strip_default', actions)

    def test_missing_saved_metrics_is_noop(self):
        target = metrics('out = sorted([3, 1])\n')
        actions = [a['action'] for a in build({}, target)['actions']]
        self.assertFalse(set(actions) & {
            'create_safe_explicit_sorted_reverse', 'create_safe_implicit_sorted_reverse',
            'create_safe_explicit_strip_default', 'create_safe_implicit_strip_default'})

    def test_mixed_saved_preference_is_ambiguous(self):
        saved = metrics('a = sorted([3, 1], reverse=False)\nb = sorted([2, 1])\n')
        target = metrics('out = sorted([3, 1])\n')
        actions = [a['action'] for a in build(saved, target)['actions']]
        self.assertNotIn('create_safe_explicit_sorted_reverse', actions)

    def test_policy_accepts_new_syntax_action(self):
        self.assertIsNotNone(get_tag_action_policy('sorted 사용', 'create_safe_explicit_sorted_reverse'))
        self.assertIsNotNone(get_tag_action_policy('문자열 메서드 호출', 'create_safe_implicit_strip_default'))

    def test_dispatch_four_actions(self):
        for action, func in (
            ('create_safe_explicit_sorted_reverse', sort_exp),
            ('create_safe_implicit_sorted_reverse', sort_imp),
            ('create_safe_explicit_strip_default', strip_exp),
            ('create_safe_implicit_strip_default', strip_imp),
        ):
            self.assertIs(_get_transform_function(action), func)


class FineSafetyTests(unittest.TestCase):
    def test_sorted_shadowing(self):
        src = 'sorted = lambda x: x\nout = sorted([2, 1])\n'
        self.assertEqual(sort_exp(src), src)

    def test_rewrite_only_literal_list(self):
        src = 'x = [2, 1]\nout = sorted(x)\n'
        self.assertEqual(sort_exp(src), src)

    def test_mixed_literal_types(self):
        src = 'out = sorted([1, "2"])\n'
        self.assertEqual(sort_exp(src), src)

    def test_unrelated_reverse_true(self):
        src = 'out = sorted([3, 2], reverse=True)\n'
        self.assertEqual(sort_imp(src), src)

    def test_strip_dynamic_receiver(self):
        src = 'out = unknown.strip()\n'
        self.assertEqual(strip_exp(src), src)

    def test_strip_explicit_char_argument(self):
        src = 'out = "abc".strip("a")\n'
        self.assertEqual(strip_imp(src), src)

    def test_nested_call_not_changed(self):
        src = 'out = print(sorted([2, 1]))\n'
        self.assertEqual(sort_exp(src), src)

    def test_unicode_and_crlf(self):
        src = 'out = "  서울  ".strip()\r\n'
        self.assertEqual(strip_exp(src), 'out = "  서울  ".strip(None)\r\n')

    def test_invalid_code_returns_unchanged(self):
        src = 'out = sorted([1,2]\n'
        self.assertEqual(sort_exp(src), src)
        self.assertEqual(strip_imp(src), src)

    def test_idempotency(self):
        src = 'out = sorted([2, 1])\n'
        self.assertEqual(sort_exp(sort_exp(src)), sort_exp(src))
        src = 'out = " hi ".strip()\n'
        self.assertEqual(strip_exp(strip_exp(src)), strip_exp(src))

    def test_round_trip(self):
        src = 'out = sorted([2, 1])\n'
        self.assertEqual(sort_imp(sort_exp(src)), src)
        src2 = 'out = " hi ".strip()\n'
        self.assertEqual(strip_imp(strip_exp(src2)), src2)


if __name__ == '__main__':
    unittest.main()
