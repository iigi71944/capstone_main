"""Batch-5 registry/plan/dispatcher and trusted-example regression tests.

These do not introduce a different storage schema or mutate frontend code.
"""
from __future__ import annotations

import ast
import contextlib
import io
import unittest

from app.services.style_tag_transform_map_service import (
    CREATE_ACTION_BY_TAG, COMPARE_ONLY_TAGS, get_tag_transform_status,
)
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_apply_service import _get_transform_function


NEW = {
    '인덱싱 사용': 'create_safe_known_key_indexing',
    '속성 접근': 'create_safe_direct_attribute',
    '키워드 인자 사용': 'create_safe_keyword_call',
    '위치 인자 사용': 'create_safe_positional_call',
}


def diff(style: dict[str, int], target: dict[str, int]) -> dict:
    return {
        'style_metrics': style,
        'target_analysis': {'metrics': target},
        'style_syntax_names': set(),
        'style_concept_names': set(),
        'target_syntax_names': set(),
        'target_concept_names': set(),
        'missing_syntax_tags': [],
        'missing_concept_tags': [],
    }


def planned(style: dict[str, int], target: dict[str, int]) -> list[str]:
    return [x['action'] for x in build_transform_plan(diff(style, target))['actions']]


def observe(source: str) -> tuple:
    output = io.StringIO()
    namespace = {}
    with contextlib.redirect_stdout(output):
        exec(compile(source, '<trusted-batch5-integration>', 'exec'), namespace)
    value = namespace.get('result')
    return (output.getvalue(), type(value).__name__, repr(value))


class RegistryChecks(unittest.TestCase):
    def test_four_tags_are_linked(self):
        for tag, action in NEW.items():
            with self.subTest(tag=tag):
                self.assertEqual(CREATE_ACTION_BY_TAG.get(tag), action)
                self.assertEqual(get_tag_transform_status(tag), 'linked')
                self.assertNotIn(tag, COMPARE_ONLY_TAGS)
                self.assertTrue(callable(_get_transform_function(action)))

    def test_old_style_storage_filter_unchanged(self):
        from app.services.style_tag_filter_service import STYLE_RELEVANT_SYNTAX_TAGS
        for tag in NEW:
            self.assertNotIn(tag, STYLE_RELEVANT_SYNTAX_TAGS)
        self.assertEqual(len(STYLE_RELEVANT_SYNTAX_TAGS), 19)

    def test_old_actions_kept(self):
        self.assertEqual(CREATE_ACTION_BY_TAG.get('리스트 리터럴'), 'create_safe_list_literal')
        self.assertEqual(CREATE_ACTION_BY_TAG.get('함수 중심 코드 구조'), 'create_function_structure')


class PlanChecks(unittest.TestCase):
    def test_indexing_preference(self):
        self.assertIn('create_safe_known_key_indexing', planned({'subscript_count': 3}, {'subscript_count': 0}))

    def test_indexing_not_when_absent(self):
        self.assertNotIn('create_safe_known_key_indexing', planned({}, {'subscript_count': 0}))

    def test_indexing_not_when_target_already_has(self):
        self.assertNotIn('create_safe_known_key_indexing', planned({'subscript_count': 2}, {'subscript_count': 1}))

    def test_attribute_preference(self):
        self.assertIn('create_safe_direct_attribute', planned({'attribute_count': 2}, {}))

    def test_attribute_not_when_target_has(self):
        self.assertNotIn('create_safe_direct_attribute', planned({'attribute_count': 2}, {'attribute_count': 1}))

    def test_keyword_preference(self):
        self.assertIn('create_safe_keyword_call', planned({'keyword_arg_count': 2}, {'keyword_arg_count': 0}))

    def test_keyword_not_when_target_has(self):
        self.assertNotIn('create_safe_keyword_call', planned({'keyword_arg_count': 2}, {'keyword_arg_count': 1}))

    def test_positional_preference(self):
        actions=planned({'positional_arg_count': 3, 'keyword_arg_count': 0}, {'keyword_arg_count': 3})
        self.assertIn('create_safe_positional_call', actions)
        self.assertNotIn('create_safe_keyword_call', actions)

    def test_positional_not_ambiguous_style(self):
        self.assertNotIn('create_safe_positional_call', planned({'positional_arg_count': 1, 'keyword_arg_count': 2}, {'keyword_arg_count': 1}))

    def test_positional_not_without_evidence(self):
        self.assertNotIn('create_safe_positional_call', planned({}, {'keyword_arg_count': 1}))

    def test_unrelated_actions_can_coexist(self):
        actions=planned({'subscript_count': 2, 'attribute_count': 2, 'keyword_arg_count': 1}, {})
        self.assertIn('create_safe_known_key_indexing', actions)
        self.assertIn('create_safe_direct_attribute', actions)
        self.assertIn('create_safe_keyword_call', actions)

    def test_metric_preference_is_not_invented(self):
        self.assertEqual(planned({}, {}), [])

    def test_existing_concept_action_deduplicates_keyword(self):
        case=diff({'keyword_arg_count': 2}, {})
        case['missing_concept_tags']=[{'tag':'함수 매개변수 활용 구조'}]
        actions=[x['action'] for x in build_transform_plan(case)['actions']]
        self.assertEqual(actions.count('create_safe_keyword_call'), 1)

    def test_existing_concept_action_deduplicates_attribute(self):
        case=diff({'attribute_count': 2}, {})
        case['missing_concept_tags']=[{'tag':'객체 접근 중심 구조'}]
        actions=[x['action'] for x in build_transform_plan(case)['actions']]
        self.assertEqual(actions.count('create_safe_direct_attribute'), 1)

    def test_conflicting_keyword_directions_fail_closed(self):
        case=diff({'positional_arg_count': 4, 'keyword_arg_count': 0}, {'keyword_arg_count': 2})
        case['missing_concept_tags']=[{'tag':'함수 매개변수 활용 구조'}]
        actions=[x['action'] for x in build_transform_plan(case)['actions']]
        self.assertNotIn('create_safe_positional_call', actions)
        self.assertNotIn('create_safe_keyword_call', actions)


class ExistingTransformerSmokeTests(unittest.TestCase):
    def changed(self, tag: str, code: str, marker: str) -> None:
        transform = _get_transform_function(NEW[tag])
        output = transform(code)
        self.assertNotEqual(code, output)
        self.assertIn(marker, output)
        ast.parse(output)
        self.assertEqual(observe(code), observe(output))
        self.assertEqual(output, transform(output))

    def unchanged(self, tag: str, code: str) -> None:
        self.assertEqual(code, _get_transform_function(NEW[tag])(code))

    def test_keyword_basic_two_parameters(self):
        self.changed('키워드 인자 사용',
                     'def add(a,b):\n    return a+b\nresult=add(1,2)\n', 'add(a=1, b=2)')

    def test_keyword_additional_three_parameters(self):
        self.changed('키워드 인자 사용',
                     'def add(a,b,c):\n    return a+b+c\nresult=add(1,2,3)\n', 'add(a=1, b=2, c=3)')

    def test_keyword_complex_multiple_calls(self):
        self.changed('키워드 인자 사용',
                     'def add(a,b):\n    return a+b\nx=add(1,2)\nresult=add(3,4)\n', 'add(a=3, b=4)')

    def test_keyword_skip_unsafe_defaults(self):
        self.unchanged('키워드 인자 사용', 'def f(x,y=2):\n    return x+y\nresult=f(1,3)\n')

    def test_positional_basic(self):
        self.changed('위치 인자 사용',
                     'def add(a,b):\n    return a+b\nresult=add(a=1,b=2)\n', 'add(1, 2)')

    def test_positional_additional_three_parameters(self):
        self.changed('위치 인자 사용',
                     'def add(a,b,c):\n    return a+b+c\nresult=add(a=1,b=2,c=3)\n', 'add(1, 2, 3)')

    def test_positional_complex_multiple_calls(self):
        self.changed('위치 인자 사용',
                     'def add(a,b):\n    return a+b\nx=add(a=1,b=2)\nresult=add(a=3,b=4)\n', 'add(3, 4)')

    def test_positional_skip_permuted_arguments(self):
        self.unchanged('위치 인자 사용', 'def f(a,b):\n    return a-b\nresult=f(b=1,a=2)\n')

    def test_attribute_basic(self):
        self.changed('속성 접근',
                     'class C: pass\no=C()\no.x=3\nresult=getattr(o,"x")\n', 'o.x')

    def test_attribute_additional_string_field(self):
        self.changed('속성 접근',
                     'class C: pass\no=C()\no.name="red"\nresult=getattr(o,"name")\n', 'o.name')

    def test_attribute_complex_two_getattr_calls(self):
        self.changed('속성 접근',
                     'class C: pass\no=C()\no.x=2\no.y=3\na=getattr(o,"x")\nresult=getattr(o,"y")\n', 'o.y')

    def test_attribute_skip_default_arg(self):
        self.unchanged('속성 접근', 'class C: pass\no=C()\nresult=getattr(o,"x",None)\n')

    def test_indexing_dispatch_basic(self):
        self.changed('인덱싱 사용', "data={'a':5}\nresult=data.get('a')\n", "data['a']")

    def test_indexing_dispatch_additional(self):
        self.changed('인덱싱 사용', "data={2:'v'}\nresult=data.get(2)\n", 'data[2]')

    def test_indexing_dispatch_complex(self):
        self.changed('인덱싱 사용', "def f():\n    data={'a':5}\n    return data.get('a')\nresult=f()\n", "data['a']")


if __name__ == '__main__':
    unittest.main()
