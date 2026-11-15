"""Finite, trusted-fixture tests for three constructor-to-literal tag actions.

Only fixed Python snippets embedded in this file are executed. This is not a
security sandbox, nor does it establish semantic equivalence for arbitrary code.
"""
from __future__ import annotations

import ast
import contextlib
import io
import unittest

from app.services.improvement.safe_unmapped_patterns_batch4_service import (
    transform_to_list_literal as as_list,
    transform_to_dict_literal as as_dict,
    transform_to_tuple_literal as as_tuple,
)


def observe(source: str) -> tuple:
    out = io.StringIO()
    variables: dict = {}
    with contextlib.redirect_stdout(out):
        exec(compile(source, '<trusted-fixed-batch4-test>', 'exec'), variables)
    value = variables.get('result')
    return (out.getvalue(), type(value).__name__, repr(value))


class Checks(unittest.TestCase):
    def changed(self, fn, code: str, marker: str) -> str:
        updated = fn(code)
        self.assertNotEqual(code, updated)
        ast.parse(updated)
        self.assertIn(marker, updated)
        self.assertEqual(observe(code), observe(updated))
        self.assertEqual(updated, fn(updated))
        return updated

    def unchanged(self, fn, code: str) -> None:
        self.assertEqual(fn(code), code)


class ListTag(Checks):
    def test_basic_empty(self):
        self.changed(as_list, 'result=list()\nprint(result)\n', 'result=[]')

    def test_additional_tuple(self):
        self.changed(as_list, 'result=list((1,2,3))\nprint(result)\n', '[1, 2, 3]')

    def test_complex_function_condition(self):
        self.changed(as_list, 'def f():\n    values=list((1,2))\n    if len(values)>1:\n        return values\nresult=f()\nprint(result)\n', 'values=[1, 2]')

    def test_list_input(self):
        self.changed(as_list, 'result=list([7,8])\n', '[7, 8]')

    def test_string_input(self):
        self.changed(as_list, "result=list('가나')\n", "['가', '나']")

    def test_bytes_input(self):
        self.changed(as_list, "result=list(b'ab')\n", '[97, 98]')

    def test_one_element(self):
        self.changed(as_list, 'result=list((3,))\n', '[3]')

    def test_negative_numbers(self):
        self.changed(as_list, 'result=list((-4, 5))\n', '[-4, 5]')

    def test_bool_none(self):
        self.changed(as_list, 'result=list((None, True, False))\n', '[None, True, False]')

    def test_multiple_independent_sites(self):
        self.changed(as_list, 'a=list()\nresult=list((2,3))\nprint(a,result)\n', 'a=[]')

    def test_comments_elsewhere_preserved(self):
        changed = self.changed(as_list, '# 시작\nresult=list((1,2))\n# 끝\n', '# 시작')
        self.assertTrue(changed.endswith('# 끝\n'))

    def test_crlf_preserved(self):
        changed = self.changed(as_list, 'result=list((1,2))\r\nprint(result)\r\n', '[1, 2]')
        self.assertNotIn('\n', changed.replace('\r\n',''))

    def test_shadowed_variable_rejected(self):
        self.unchanged(as_list, 'list=lambda x:x\nresult=list((1,2))\n')

    def test_shadowed_parameter_rejected(self):
        self.unchanged(as_list, 'def f(list):\n    return list((1,2))\n')

    def test_shadowed_function_rejected(self):
        self.unchanged(as_list, 'def list():\n    pass\nresult=list()\n')

    def test_unknown_iterable_rejected(self):
        self.unchanged(as_list, 'def f(items):\n    return list(items)\n')

    def test_side_effect_rejected(self):
        self.unchanged(as_list, 'result=list([get_item()])\n')

    def test_multiline_constructor_rejected(self):
        self.unchanged(as_list, 'result=list(\n    (1,2)\n)\n')

    def test_comment_on_line_rejected(self):
        self.unchanged(as_list, 'result=list((1,2))  # keep\n')

    def test_overlong_literal_rejected(self):
        self.unchanged(as_list, 'result=list(tuple(range(100)))\n')

    def test_is_observation_rejected(self):
        self.unchanged(as_list, 'result=list()\nprint(result is result)\n')

    def test_locals_observation_rejected(self):
        self.unchanged(as_list, 'result=list()\nprint(locals())\n')

    def test_invalid_python_unchanged(self):
        self.unchanged(as_list, 'if:')


class DictTag(Checks):
    def test_basic_empty(self):
        self.changed(as_dict, 'result=dict()\nprint(result)\n', 'result={}')

    def test_additional_keywords(self):
        self.changed(as_dict, 'result=dict(a=1,b=2)\nprint(result)\n', "{'a': 1, 'b': 2}")

    def test_complex_function_pairs(self):
        self.changed(as_dict, 'def f():\n    d=dict([("a",1),("b",2)])\n    return d\nresult=f()\nprint(result)\n', '{"a": 1, "b": 2}')

    def test_tuple_of_pairs(self):
        self.changed(as_dict, "result=dict((('x',3),('y',4)))\n", "{'x': 3, 'y': 4}")

    def test_duplicate_literal_keys(self):
        self.changed(as_dict, "result=dict([('x',1),('x',2)])\n", "{'x': 1, 'x': 2}")

    def test_negative_key(self):
        self.changed(as_dict, 'result=dict([(-2,"neg")])\n', '{-2: "neg"}')

    def test_bool_key(self):
        self.changed(as_dict, 'result=dict([(True,9)])\n', '{True: 9}')

    def test_none_key(self):
        self.changed(as_dict, 'result=dict([(None,"none")])\n', '{None: "none"}')

    def test_mixed_literal_values(self):
        self.changed(as_dict, 'result=dict(a=True,b=None,c=-3)\n', "'a': True")

    def test_unicode(self):
        self.changed(as_dict, "result=dict(이름='민수')\nprint(result)\n", "'이름': '민수'")

    def test_preserve_unrelated_comments(self):
        changed = self.changed(as_dict, '# 전에\nresult=dict(k=1)\n# 후에\n', '# 전에')
        self.assertIn('# 후에', changed)

    def test_crlf(self):
        changed = self.changed(as_dict, 'result=dict(a=1)\r\n', "{'a': 1}")
        self.assertNotIn('\n', changed.replace('\r\n',''))

    def test_shadowed_dict_rejected(self):
        self.unchanged(as_dict, 'dict=lambda **kw: kw\nresult=dict(a=1)\n')

    def test_custom_alias_rejected(self):
        self.unchanged(as_dict, 'def f(dict):\n    return dict(a=1)\n')

    def test_dynamic_value_rejected(self):
        self.unchanged(as_dict, 'result=dict(a=compute())\n')

    def test_unpack_keyword_rejected(self):
        self.unchanged(as_dict, 'result=dict(**data)\n')

    def test_bad_key_expression_rejected(self):
        self.unchanged(as_dict, 'result=dict([(make_key(), 1)])\n')

    def test_key_tuple_rejected(self):
        self.unchanged(as_dict, 'result=dict([((1,2), 3)])\n')

    def test_pairs_malformed_rejected(self):
        self.unchanged(as_dict, 'result=dict([(1,2,3)])\n')

    def test_multiline_rejected(self):
        self.unchanged(as_dict, 'result=dict(\n    a=1\n)\n')

    def test_inline_comment_rejected(self):
        self.unchanged(as_dict, 'result=dict(a=1) # preserve\n')

    def test_is_rejected(self):
        self.unchanged(as_dict, 'result=dict()\nprint(result is result)\n')

    def test_invalid_unchanged(self):
        self.unchanged(as_dict, 'def:')


class TupleTag(Checks):
    def test_basic_empty(self):
        self.changed(as_tuple, 'result=tuple()\nprint(result)\n', 'result=()')

    def test_additional_list(self):
        self.changed(as_tuple, 'result=tuple([1,2])\nprint(result)\n', '(1, 2)')

    def test_complex_function(self):
        self.changed(as_tuple, 'def f():\n    values=tuple([1,2,3])\n    if len(values)>2:\n        return values\nresult=f()\n', 'values=(1, 2, 3)')

    def test_singleton(self):
        self.changed(as_tuple, 'result=tuple([5])\n', '(5,)')

    def test_string(self):
        self.changed(as_tuple, "result=tuple('ab')\n", "('a', 'b')")

    def test_unicode(self):
        self.changed(as_tuple, "result=tuple('가나')\n", "('가', '나')")

    def test_bytes(self):
        self.changed(as_tuple, "result=tuple(b'ab')\n", '(97, 98)')

    def test_negative_numbers(self):
        self.changed(as_tuple, 'result=tuple([-1,-2])\n', '(-1, -2)')

    def test_bool_none(self):
        self.changed(as_tuple, 'result=tuple([None,False,True])\n', '(None, False, True)')

    def test_multiple(self):
        changed = self.changed(as_tuple, 'a=tuple()\nresult=tuple([1,2])\n', 'a=()')
        self.assertIn('(1, 2)', changed)

    def test_comments_preserved(self):
        changed = self.changed(as_tuple, '# 위\nresult=tuple([1,2])\n# 아래\n', '# 위')
        self.assertTrue(changed.endswith('# 아래\n'))

    def test_crlf(self):
        changed = self.changed(as_tuple, 'result=tuple([1,2])\r\n', '(1, 2)')
        self.assertNotIn('\n', changed.replace('\r\n',''))

    def test_shadowed_rejected(self):
        self.unchanged(as_tuple, 'tuple=lambda v:v\nresult=tuple([1,2])\n')

    def test_parameter_shadow_rejected(self):
        self.unchanged(as_tuple, 'def f(tuple):\n    return tuple([1,2])\n')

    def test_unknown_generator_rejected(self):
        self.unchanged(as_tuple, 'result=tuple(i for i in range(3))\n')

    def test_dynamic_list_rejected(self):
        self.unchanged(as_tuple, 'result=tuple([call()])\n')

    def test_long_str_rejected(self):
        self.unchanged(as_tuple, "result=tuple('abcdefghijklmnopqrstuvwxyz')\n")

    def test_multiline_rejected(self):
        self.unchanged(as_tuple, 'result=tuple(\n    [1,2]\n)\n')

    def test_comment_inline_rejected(self):
        self.unchanged(as_tuple, 'result=tuple([1,2]) # keep\n')

    def test_identity_observation_rejected(self):
        self.unchanged(as_tuple, 'result=tuple([1,2])\na=result is result\n')

    def test_id_rejected(self):
        self.unchanged(as_tuple, 'result=tuple([1,2])\nprint(id(result))\n')

    def test_invalid_rejected(self):
        self.unchanged(as_tuple, 'a=')


class Integration(unittest.TestCase):
    """These cases load the real transformed project after the installer runs."""

    def _diff(self, name: str, saved_count: int, target_count: int) -> dict:
        return {
            'missing_syntax_tags': [], 'missing_concept_tags': [],
            'style_syntax_names': set(), 'style_concept_names': set(),
            'target_syntax_names': set(), 'target_concept_names': set(),
            'style_metrics': {name: saved_count},
            'target_analysis': {'metrics': {name: target_count}},
        }

    def test_list_tag_wiring(self):
        from app.services.style_tag_transform_map_service import get_create_action_for_tag
        self.assertEqual(get_create_action_for_tag('리스트 리터럴'), 'create_safe_list_literal')

    def test_dict_tag_wiring(self):
        from app.services.style_tag_transform_map_service import get_create_action_for_tag
        self.assertEqual(get_create_action_for_tag('딕셔너리 리터럴'), 'create_safe_dict_literal')

    def test_tuple_tag_wiring(self):
        from app.services.style_tag_transform_map_service import get_create_action_for_tag
        self.assertEqual(get_create_action_for_tag('튜플 리터럴'), 'create_safe_tuple_literal')

    def test_list_action_planned_from_metrics(self):
        from app.services.style_transform_plan_service import build_transform_plan
        actions = build_transform_plan(self._diff('list_literal_count', 1, 0))['actions']
        self.assertIn('create_safe_list_literal', [x.get('action') for x in actions])

    def test_dict_action_planned_from_metrics(self):
        from app.services.style_transform_plan_service import build_transform_plan
        actions = build_transform_plan(self._diff('dict_literal_count', 1, 0))['actions']
        self.assertIn('create_safe_dict_literal', [x.get('action') for x in actions])

    def test_tuple_action_planned_from_metrics(self):
        from app.services.style_transform_plan_service import build_transform_plan
        actions = build_transform_plan(self._diff('tuple_literal_count', 1, 0))['actions']
        self.assertIn('create_safe_tuple_literal', [x.get('action') for x in actions])

    def test_no_invented_preference_when_saved_zero(self):
        from app.services.style_transform_plan_service import build_transform_plan
        for name in ('list_literal_count', 'dict_literal_count', 'tuple_literal_count'):
            with self.subTest(name=name):
                actions = build_transform_plan(self._diff(name, 0, 0))['actions']
                self.assertNotIn('create_safe_' + name.replace('_literal_count', '_literal'),
                                 [x.get('action') for x in actions])

    def test_no_unnecessary_transform_when_target_already_uses_literal(self):
        from app.services.style_transform_plan_service import build_transform_plan
        for name in ('list_literal_count', 'dict_literal_count', 'tuple_literal_count'):
            with self.subTest(name=name):
                actions = build_transform_plan(self._diff(name, 1, 1))['actions']
                self.assertFalse(any(item.get('action', '').startswith('create_safe_') and
                                     item.get('action', '').endswith('_literal')
                                     for item in actions))

    def test_dispatch_links_to_real_transforms(self):
        from app.services.style_apply_service import _get_transform_function
        self.assertIs(_get_transform_function('create_safe_list_literal'), as_list)
        self.assertIs(_get_transform_function('create_safe_dict_literal'), as_dict)
        self.assertIs(_get_transform_function('create_safe_tuple_literal'), as_tuple)

    def test_registry_audit_still_ok(self):
        from app.services.style_transform_audit_service import audit_style_registry
        report = audit_style_registry()
        self.assertEqual(report['status'], 'ok', report.get('issues'))

    def test_real_diff_stored_list_preference(self):
        from app.services.style_diff_service import compare_style_with_target_code
        from app.services.style_transform_plan_service import build_transform_plan
        style = {'syntax_tags': [], 'concept_tags': [], 'metrics': {'list_literal_count': 1}}
        diff = compare_style_with_target_code(style, 'result=list((1,2))\nprint(result)\n')
        self.assertIn('create_safe_list_literal', [a['action'] for a in build_transform_plan(diff)['actions']])


if __name__ == '__main__':
    unittest.main()
