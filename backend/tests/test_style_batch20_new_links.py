"""Batch 20 positive triplets, safety gates, planning and dispatcher integration."""
from __future__ import annotations

import ast
import unittest

from app.services.improvement.safe_batch20_service import (
    transform_safe_empty_dict_get_to_none as none_transform,
    transform_safe_builtins_print_to_print as print_transform,
)
from app.services.style_tag_transform_map_service import (
    CREATE_ACTION_BY_TAG, COMPARE_ONLY_TAGS, get_create_action_for_tag,
)
from app.services.style_apply_service import _get_transform_function
from app.services.style_transform_plan_service import build_transform_plan


def plan(saved=None, target=None, missing=None):
    return build_transform_plan({
        'missing_syntax_tags': missing or [], 'missing_concept_tags': [],
        'style_syntax_names': set(), 'style_concept_names': set(),
        'target_syntax_names': set(), 'target_concept_names': set(),
        'style_metrics': saved or {},
        'target_analysis': {'metrics': target or {}},
    })


class NoneTagTriplets(unittest.TestCase):
    def test_basic(self):
        source = 'value = {}.get("missing")\n'
        self.assertEqual(none_transform(source), 'value = None\n')

    def test_additional(self):
        source = 'zero = {}.get(0)\n'
        self.assertEqual(none_transform(source), 'zero = None\n')

    def test_complex(self):
        source = 'first = {}.get("없는 키")  # keep\nsecond = {}.get(False)\n'
        result = none_transform(source)
        self.assertEqual(result, 'first = None  # keep\nsecond = None\n')


class PrintTagTriplets(unittest.TestCase):
    def test_basic(self):
        source = 'import builtins\nbuiltins.print("Hello")\n'
        self.assertEqual(print_transform(source), 'import builtins\nprint("Hello")\n')

    def test_additional(self):
        source = 'import builtins\nbuiltins.print(3, 4)  # keep\n'
        self.assertEqual(print_transform(source), 'import builtins\nprint(3, 4)  # keep\n')

    def test_complex(self):
        source = 'import builtins\nbuiltins.print("한글", sep=":")\nbuiltins.print(7, end="!")\n'
        result = print_transform(source)
        self.assertEqual(result, 'import builtins\nprint("한글", sep=":")\nprint(7, end="!")\n')


class Batch20Safety(unittest.TestCase):
    def test_none_nonempty_dict_unchanged(self):
        s = 'value = {"x": 4}.get("x")\n'
        self.assertEqual(none_transform(s), s)

    def test_none_dynamic_key_unchanged(self):
        s = 'value = {}.get(process())\n'
        self.assertEqual(none_transform(s), s)

    def test_none_default_argument_unchanged(self):
        s = 'value = {}.get("x", 123)\n'
        self.assertEqual(none_transform(s), s)

    def test_none_nested_assignment_unchanged(self):
        s = 'def f():\n    return {}.get("x")\n'
        self.assertEqual(none_transform(s), s)

    def test_none_expression_statement_unchanged(self):
        s = '{}.get("x")\n'
        self.assertEqual(none_transform(s), s)

    def test_none_multiline_call_unchanged(self):
        s = 'v = {}.get(\n    "x"\n)\n'
        self.assertEqual(none_transform(s), s)

    def test_print_no_prior_import(self):
        s = 'builtins.print("x")\nimport builtins\n'
        self.assertEqual(print_transform(s), s)

    def test_print_aliased_import(self):
        s = 'import builtins as b\nbuiltins.print("x")\n'
        self.assertEqual(print_transform(s), s)

    def test_print_shadowed(self):
        s = 'import builtins\nprint = lambda x: None\nbuiltins.print("x")\n'
        self.assertEqual(print_transform(s), s)

    def test_print_module_rebound(self):
        s = 'import builtins\nbuiltins = None\nbuiltins.print("x")\n'
        self.assertEqual(print_transform(s), s)

    def test_print_attribute_overridden(self):
        s = 'import builtins\nbuiltins.print = fake\nbuiltins.print("x")\n'
        self.assertEqual(print_transform(s), s)

    def test_print_dynamic_globals_rejected(self):
        s = 'import builtins\nglobals()["print"] = bad\nbuiltins.print("x")\n'
        self.assertEqual(print_transform(s), s)

    def test_print_builtins_dict_rebinding_rejected(self):
        s = 'import builtins\nbuiltins.__dict__["print"] = fake\nbuiltins.print("x")\n'
        self.assertEqual(print_transform(s), s)

    def test_print_dunder_setattr_rejected(self):
        s = 'import builtins\nbuiltins.__setattr__("print", fake)\nbuiltins.print("x")\n'
        self.assertEqual(print_transform(s), s)

    def test_print_in_function_not_rewritten(self):
        s = 'import builtins\ndef f():\n    builtins.print("x")\n'
        self.assertEqual(print_transform(s), s)

    def test_print_import_star_rejected(self):
        s = 'import builtins\nfrom other import *\nbuiltins.print("x")\n'
        self.assertEqual(print_transform(s), s)

    def test_print_duplicate_import_rejected(self):
        s = 'import builtins\nimport builtins\nbuiltins.print(1)\n'
        self.assertEqual(print_transform(s), s)

    def test_invalid_python_unchanged(self):
        s = 'def broken(\n'
        self.assertEqual(print_transform(s), s)
        self.assertEqual(none_transform(s), s)

    def test_crlf_preserved(self):
        self.assertEqual(none_transform('x = {}.get(2)\r\n'), 'x = None\r\n')
        self.assertEqual(print_transform('import builtins\r\nbuiltins.print(2)\r\n'), 'import builtins\r\nprint(2)\r\n')

    def test_registrations_and_dispatch(self):
        self.assertEqual(get_create_action_for_tag('None 사용'), 'create_safe_empty_dict_none')
        self.assertEqual(get_create_action_for_tag('print 사용'), 'create_safe_builtin_print')
        self.assertIs(_get_transform_function('create_safe_empty_dict_none'), none_transform)
        self.assertIs(_get_transform_function('create_safe_builtin_print'), print_transform)
        self.assertEqual(len(CREATE_ACTION_BY_TAG), 82)
        self.assertEqual(len(COMPARE_ONLY_TAGS), 20)

    def test_preference_gate_for_none(self):
        actions = {item['action'] for item in plan(
            {'none_count': 1},
            {'none_count': 0, 'dict_literal_count': 1, 'attribute_count': 1, 'call_count': 1},
        )['actions']}
        self.assertIn('create_safe_empty_dict_none', actions)

    def test_preference_gate_for_print(self):
        actions = {item['action'] for item in plan(
            {'print_call_count': 1},
            {'print_call_count': 0, 'attribute_count': 1, 'call_count': 1, 'import_count': 1},
        )['actions']}
        self.assertIn('create_safe_builtin_print', actions)

    def test_missing_tag_without_metrics_does_not_generate(self):
        actions = {item['action'] for item in plan(
            {}, {'call_count': 3, 'import_count': 1, 'attribute_count': 1},
            missing=[{'tag': 'None 사용'}, {'tag': 'print 사용'}],
        )['actions']}
        self.assertNotIn('create_safe_empty_dict_none', actions)
        self.assertNotIn('create_safe_builtin_print', actions)

    def test_target_preference_already_present(self):
        actions = {item['action'] for item in plan(
            {'none_count': 1, 'print_call_count': 1},
            {'none_count': 1, 'print_call_count': 1, 'attribute_count': 2, 'call_count': 2, 'import_count': 1, 'dict_literal_count': 1},
        )['actions']}
        self.assertNotIn('create_safe_empty_dict_none', actions)
        self.assertNotIn('create_safe_builtin_print', actions)

    def test_old_tags_do_not_change(self):
        for tag, action in {
            '비교 연산': 'create_safe_operator_comparison',
            '함수 호출': 'create_safe_operator_call',
            'continue문': 'create_safe_guard_continue',
        }.items():
            self.assertEqual(get_create_action_for_tag(tag), action)

    def test_actual_semantics_for_safe_literal(self):
        for initial in ('v = {}.get("missing")\n', 'v = {}.get(3)\n'):
            changed = none_transform(initial)
            left, right = {}, {}
            exec(initial, left)
            exec(changed, right)
            self.assertIsNone(left['v'])
            self.assertIsNone(right['v'])
            ast.parse(changed)


if __name__ == '__main__':
    unittest.main()
