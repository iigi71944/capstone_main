"""Batch 30: verified shared-tag policy and granular variant conflict matrix.

48 pair-level cases (16 families x basic/additional/complex),
12 fine-variant cases (4 directions x basic/additional/complex),
12 compatibility, execution and conflict checks.
No frontend or saved-style schema changes are needed.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import unittest

from app.services.metric_service import calculate_metrics
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_action_policy_service import (
    SHARED_TAG_FAMILIES, TAG_ACTION_POLICIES,
    get_tag_action_policy, finalize_tag_action_policies,
)
from app.services.style_tag_transform_map_service import (
    COMPARE_ONLY_TAGS, CREATE_ACTION_BY_TAG,
)
from app.services.style_transform_plan_service import (
    _resolve_new_family_actions, build_transform_plan,
)


def _item(tag, action=None):
    return {'tag': tag, 'action': action or CREATE_ACTION_BY_TAG[tag],
            'reason': 'Batch30 regression fixture'}


def _plan(saved, target):
    return build_transform_plan({
        'style_metrics': saved,
        'target_analysis': {'metrics': target},
        'style_syntax_names': set(), 'style_concept_names': set(),
        'target_syntax_names': set(), 'target_concept_names': set(),
        'missing_syntax_tags': [], 'missing_concept_tags': [],
    })


def _metrics(src):
    return calculate_metrics(ast.parse(src))


def _run(src):
    p = subprocess.run([sys.executable, '-I', '-c', src],
                       text=True, capture_output=True, timeout=4)
    return p.returncode, p.stdout, p.stderr


class SharedTagPolicyTriplets(unittest.TestCase):
    """Populated below: each of 16 independent pairs gets three tests."""


def _shared_basic(self, family):
    tags = SHARED_TAG_FAMILIES[family]
    left, right = [get_tag_action_policy(t) for t in tags]
    self.assertNotEqual(left['policy_action'], right['policy_action'])
    self.assertEqual(left['family'], family)
    self.assertEqual(right['family'], family)
    self.assertIn(left['role'], {'syntax_limit', 'concept_structure'})
    self.assertIn(right['role'], {'syntax_limit', 'concept_structure'})
    for tag in tags:
        action = CREATE_ACTION_BY_TAG[tag]
        self.assertIn(action, TAG_ACTION_POLICIES[tag]['allowed_actions'])
        self.assertTrue(callable(_get_transform_function(action)))


def _shared_additional(self, family):
    a, b = SHARED_TAG_FAMILIES[family]
    chosen = []
    for tags in ((a, b), (b, a)):
        output = finalize_tag_action_policies([_item(t) for t in tags])
        self.assertEqual(len(output), 1)
        row = output[0]
        self.assertEqual(row['policy_family'], family)
        self.assertEqual(set(row['policy_source_tags']), {a, b})
        self.assertEqual(len(row['policy_source_tags']), 2)
        self.assertEqual(finalize_tag_action_policies(output), output)
        chosen.append((row['tag'], row['action']))
    self.assertEqual(chosen[0], chosen[1])


def _shared_complex(self, family):
    a, b = SHARED_TAG_FAMILIES[family]
    other_family = next(k for k in SHARED_TAG_FAMILIES if k != family)
    c, d = SHARED_TAG_FAMILIES[other_family]
    unrelated = {'tag': '__test_unrelated__', 'action': '__keep__', 'reason': 'unrelated'}
    reverse = _item(a, '__unknown_reverse__')
    source = [_item(a), unrelated, reverse, _item(c), _item(b), _item(d)]
    snapshot = [dict(row) for row in source]
    output = finalize_tag_action_policies(source)
    self.assertEqual(source, snapshot, 'policy selection must not modify input')
    picked = [row for row in output if row.get('policy_family') == family]
    another = [row for row in output if row.get('policy_family') == other_family]
    self.assertEqual(len(picked), 1)
    self.assertEqual(len(another), 1)
    self.assertEqual(set(picked[0]['policy_source_tags']), {a, b})
    self.assertEqual(set(another[0]['policy_source_tags']), {c, d})
    self.assertIn(unrelated, output)
    self.assertIn(reverse, output, 'unrelated reverse action may not be swallowed')
    self.assertEqual(finalize_tag_action_policies(output), output)


def _make_shared(level, family):
    fn = {'basic': _shared_basic, 'additional': _shared_additional,
          'complex': _shared_complex}[level]
    def test(self):
        fn(self, family)
    test.__name__ = f'test_{family}_{level}'
    return test


# Stable test IDs are used by audit_transform_batch30.py.
for _family in SHARED_TAG_FAMILIES:
    for _level in ('basic', 'additional', 'complex'):
        setattr(SharedTagPolicyTriplets, f'test_{_family}_{_level}',
                _make_shared(_level, _family))


# Separate semantic directions share a tag but MUST NOT be merged as the same
# desired code style. Each variant is verified against actual Python execution.
FINE = {
    'sorted_explicit': (
        'sorted 사용', 'create_safe_explicit_sorted_reverse',
        'a = sorted([3, 1, 2])\nprint(a)\n',
        'a = sorted([3, 1, 2], reverse=False)\nprint(a)\n',
        'b = sorted([9, 4])\nprint(b)\n',
    ),
    'sorted_implicit': (
        'sorted 사용', 'create_safe_implicit_sorted_reverse',
        'a = sorted([3, 1, 2], reverse=False)\nprint(a)\n',
        'a = sorted([3, 1, 2])\nprint(a)\n',
        'b = sorted([9, 4], reverse=False)\nprint(b)\n',
    ),
    'strip_explicit': (
        '문자열 메서드 호출', 'create_safe_explicit_strip_default',
        'a = " hello ".strip()\nprint(a)\n',
        'a = " hello ".strip(None)\nprint(a)\n',
        'b = "  서울  ".strip()\nprint(b)\n',
    ),
    'strip_implicit': (
        '문자열 메서드 호출', 'create_safe_implicit_strip_default',
        'a = " hello ".strip(None)\nprint(a)\n',
        'a = " hello ".strip()\nprint(a)\n',
        'b = "  서울  ".strip(None)\nprint(b)\n',
    ),
}


class FineDirectionTriplets(unittest.TestCase):
    """Populated below: four independent default-argument directions."""


def _fine_basic(self, variant):
    tag, action, src, expected, extra = FINE[variant]
    transform = _get_transform_function(action)
    self.assertTrue(callable(transform))
    self.assertEqual(transform(src), expected)
    self.assertEqual(_run(src), _run(expected))
    self.assertEqual(transform(expected), expected, 'idempotent direction')
    self.assertIsNotNone(get_tag_action_policy(tag, action))


def _fine_additional(self, variant):
    tag, action, src, expected, extra = FINE[variant]
    reverse = {
        'sorted_explicit': 'create_safe_implicit_sorted_reverse',
        'sorted_implicit': 'create_safe_explicit_sorted_reverse',
        'strip_explicit': 'create_safe_implicit_strip_default',
        'strip_implicit': 'create_safe_explicit_strip_default',
    }[variant]
    actions = [a['action'] for a in _plan(_metrics(expected), _metrics(src))['actions']]
    self.assertIn(action, actions)
    self.assertNotIn(reverse, actions)
    self.assertEqual(actions.count(action), 1)
    selected = finalize_tag_action_policies([_item(tag), _item(tag, action)])
    self.assertEqual(len(selected), 1)
    self.assertEqual(selected[0]['action'], action)
    self.assertEqual(selected[0]['policy_role'], 'syntax_limit')


def _fine_complex(self, variant):
    tag, action, src, expected, extra = FINE[variant]
    combined = src + extra
    transform = _get_transform_function(action)
    result = transform(combined)
    self.assertNotEqual(result, combined)
    ast.parse(result)
    self.assertEqual(_run(combined), _run(result))
    self.assertEqual(transform(result), result)
    if 'sorted' in variant:
        self.assertIn('sorted', result)
        self.assertIn('print', result)
    else:
        self.assertIn('.strip', result)
        self.assertIn('print', result)


def _make_fine(level, variant):
    fn = {'basic': _fine_basic, 'additional': _fine_additional,
          'complex': _fine_complex}[level]
    def test(self):
        fn(self, variant)
    test.__name__ = f'test_{variant}_{level}'
    return test


for _variant in FINE:
    for _level in ('basic', 'additional', 'complex'):
        setattr(FineDirectionTriplets, f'test_{_variant}_{_level}',
                _make_fine(_level, _variant))


class ConflictCompatibilityTests(unittest.TestCase):
    """Twelve additional cross-family and backward-compatibility checks."""

    def test_01_tag_count_and_29_metric_schema(self):
        self.assertEqual((len(CREATE_ACTION_BY_TAG), len(COMPARE_ONLY_TAGS)), (102, 0))
        data = _metrics('a = " hi ".strip(None)\n')
        self.assertEqual(data['strip_none_explicit_count'], 1)
        self.assertIn('list_extend_call_count', data)

    def test_02_old_missing_metric_is_noop(self):
        target = _metrics('out = sorted([2, 1])\n')
        acts = {x['action'] for x in _plan({}, target)['actions']}
        self.assertTrue(acts.isdisjoint({
            'create_safe_explicit_sorted_reverse', 'create_safe_implicit_sorted_reverse',
            'create_safe_explicit_strip_default', 'create_safe_implicit_strip_default'}))

    def test_03_mixed_saved_sorted_style_is_not_guessed(self):
        saved = _metrics('a = sorted([2, 1])\nb = sorted([3, 1], reverse=False)\n')
        target = _metrics('a = sorted([1, 2])\n')
        acts = {x['action'] for x in _plan(saved, target)['actions']}
        self.assertNotIn('create_safe_explicit_sorted_reverse', acts)
        self.assertNotIn('create_safe_implicit_sorted_reverse', acts)

    def test_04_mixed_saved_strip_style_is_not_guessed(self):
        saved = _metrics('a = " a ".strip()\nb = " b ".strip(None)\n')
        target = _metrics('a = " a ".strip()\n')
        acts = {x['action'] for x in _plan(saved, target)['actions']}
        self.assertNotIn('create_safe_explicit_strip_default', acts)
        self.assertNotIn('create_safe_implicit_strip_default', acts)

    def test_05_opposite_sorted_directions_conflict(self):
        acts = [_item('sorted 사용', 'create_safe_explicit_sorted_reverse'),
                _item('sorted 사용', 'create_safe_implicit_sorted_reverse')]
        resolved = _resolve_new_family_actions(acts)
        self.assertEqual(resolved, [])

    def test_06_opposite_strip_directions_conflict(self):
        acts = [_item('문자열 메서드 호출', 'create_safe_explicit_strip_default'),
                _item('문자열 메서드 호출', 'create_safe_implicit_strip_default')]
        resolved = _resolve_new_family_actions(acts)
        self.assertEqual(resolved, [])

    def test_07_sort_and_strip_coexist_without_cross_family_suppression(self):
        saved = _metrics('a = sorted([3, 1], reverse=False)\n'
                         'b = " hi ".strip(None)\n')
        target = _metrics('a = sorted([3, 1])\n'
                          'b = " hi ".strip()\n')
        plan = _plan(saved, target)
        actions = [x['action'] for x in plan['actions']]
        self.assertEqual(actions.count('create_safe_explicit_sorted_reverse'), 1)
        self.assertEqual(actions.count('create_safe_explicit_strip_default'), 1)
        self.assertEqual(len({x.get('policy_family') for x in plan['actions']}), 2)

    def test_08_real_code_both_fine_actions_preserve_output(self):
        src = 'a = sorted([3, 1])\nb = " hi ".strip()\nprint(a, b)\n'
        changed = _get_transform_function('create_safe_explicit_sorted_reverse')(src)
        changed = _get_transform_function('create_safe_explicit_strip_default')(changed)
        self.assertIn('reverse=False', changed)
        self.assertIn('.strip(None)', changed)
        self.assertEqual(_run(src), _run(changed))

    def test_09_mismatched_method_receiver_is_not_rewritten(self):
        src = 'def f(obj):\n    return obj.strip()\n'
        transformed = _get_transform_function('create_safe_explicit_strip_default')(src)
        self.assertEqual(transformed, src)

    def test_10_dynamic_sorted_parameter_is_not_rewritten(self):
        src = 'values = [3, 2, 1]\nout = sorted(values)\n'
        transformed = _get_transform_function('create_safe_explicit_sorted_reverse')(src)
        self.assertEqual(transformed, src)

    def test_11_unknown_reverse_action_is_preserved(self):
        source = [_item('if문', 'create_conditional_expression'),
                  _item('if문'), _item('조건문 중심 구조')]
        result = finalize_tag_action_policies(source)
        self.assertIn(source[0], result)
        self.assertEqual(len(result), 2)

    def test_12_public_registry_and_saved_tag_names_are_unchanged(self):
        self.assertNotIn('sorted_reverse_explicit', CREATE_ACTION_BY_TAG)
        self.assertNotIn('strip_none_implicit', CREATE_ACTION_BY_TAG)
        for pair in SHARED_TAG_FAMILIES.values():
            for name in pair:
                self.assertIn(name, CREATE_ACTION_BY_TAG)


if __name__ == '__main__':
    unittest.main()
