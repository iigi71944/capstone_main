"""Regression tests for three previously compare-only concept tags, batch 2.

Execute only locally defined, fixed and trusted examples. No user code input.
"""
from __future__ import annotations

import ast
import contextlib
import io
import unittest

from app.services.improvement.safe_unmapped_patterns_batch2_service import (
    transform_to_data_comprehension as data_transform,
    transform_to_validation_condition as validation_transform,
    transform_to_builtin_sum as builtin_transform,
)


def observed(source: str) -> tuple[str, object]:
    buf = io.StringIO()
    namespace: dict = {}
    with contextlib.redirect_stdout(buf):
        exec(compile(source, '<trusted-static-batch2-test>', 'exec'), namespace)
    return buf.getvalue(), namespace.get('result')


class SharedAssertions(unittest.TestCase):
    def changed_and_equivalent(self, func, source: str) -> str:
        output = func(source)
        self.assertNotEqual(output, source)
        ast.parse(output)
        self.assertEqual(observed(source), observed(output))
        self.assertEqual(func(output), output)
        return output


class DataTransformTests(SharedAssertions):
    def test_basic_abs(self):
        code = 'values=[-2,1,-4]\nresult=list(map(abs,values))\nprint(result)\n'
        self.assertIn('for __capstone_map_item_0 in values', self.changed_and_equivalent(data_transform,code))

    def test_additional_str(self):
        self.changed_and_equivalent(data_transform,'result=list(map(str,[1,2,3]))\nprint(result)\n')

    def test_complex_inside_function(self):
        self.changed_and_equivalent(data_transform,'def f(values):\n    return list(map(int, values))\nresult=f(["1","2"])\nprint(result)\n')

    def test_tuple_iterable(self):
        self.changed_and_equivalent(data_transform,'result=list(map(abs,(-3,4)))\nprint(result)\n')

    def test_unicode_before_after(self):
        source='# 앞\n값=[-5]\nresult=list(map(abs,값))\n# 뒤\nprint(result)\n'
        out=self.changed_and_equivalent(data_transform,source)
        self.assertTrue(out.startswith('# 앞\n'))
        self.assertIn('# 뒤\n',out)

    def test_crlf(self):
        source='값=[-2,1]\r\nresult=list(map(abs, 값))\r\nprint(result)\r\n'
        out=self.changed_and_equivalent(data_transform,source)
        self.assertNotIn('\n',out.replace('\r\n',''))

    def test_no_map_call(self):
        code='result=[1,2]\n';self.assertEqual(data_transform(code),code)

    def test_map_shadowed(self):
        code='map=lambda *args: [99]\nresult=list(map(abs,[3]))\n'
        self.assertEqual(data_transform(code),code)

    def test_abs_shadowed(self):
        code='abs=lambda x:x\nresult=list(map(abs,[-3]))\n'
        self.assertEqual(data_transform(code),code)

    def test_list_shadowed(self):
        code='list=lambda x:x\nresult=list(map(abs,[-3]))\n'
        self.assertEqual(data_transform(code),code)

    def test_comment_on_call_line(self):
        code='result=list(map(abs,[-3])) # preserve\n'
        self.assertEqual(data_transform(code),code)

    def test_user_callable_rejected(self):
        code='def custom(x):return x\nresult=list(map(custom,[2]))\n'
        self.assertEqual(data_transform(code),code)

    def test_unsafe_dynamic_rejected(self):
        code='result=list(map(abs,[-3]))\nprint(locals())\n'
        self.assertEqual(data_transform(code),code)

    def test_no_collision_with_item_name(self):
        code='__capstone_map_item_0=123\nresult=list(map(abs,[-3]))\nprint(result)\n'
        out=self.changed_and_equivalent(data_transform,code)
        self.assertIn('__capstone_map_item_1',out)

    def test_invalid_noop(self):
        self.assertEqual(data_transform('if:'),'if:')


class ValidationTransformTests(SharedAssertions):
    def test_basic_two_nested(self):
        code='a=True\nb=True\nif a:\n    if b:\n        print("pass")\n'
        out=self.changed_and_equivalent(validation_transform,code)
        self.assertIn('if (a) and (b):',out)

    def test_additional_three_nested(self):
        code='a=b=c=True\nif a:\n    if b:\n        if c:\n            print(1)\n'
        out=self.changed_and_equivalent(validation_transform,code)
        self.assertIn('and (c)',out)

    def test_complex_in_function(self):
        code='def f(x,y):\n    if x>1:\n        if y<3:\n            return 1\n    return 0\nresult=f(2,1)\nprint(result)\n'
        out=self.changed_and_equivalent(validation_transform,code)
        self.assertIn('if (x>1) and (y<3):',out)

    def test_outer_other_if_remains(self):
        code='a=b=True\nif a:\n    if b:\n        print("ok")\nprint("last")\n'
        out=self.changed_and_equivalent(validation_transform,code)
        self.assertIn('print("last")',out)

    def test_crlf(self):
        source='a=b=True\r\nif a:\r\n    if b:\r\n        print(3)\r\n'
        out=self.changed_and_equivalent(validation_transform,source)
        self.assertNotIn('\n',out.replace('\r\n',''))

    def test_comment_inside_skip(self):
        source='if a:\n    # comment\n    if b:\n        print(1)\n'
        self.assertEqual(validation_transform(source),source)

    def test_else_skip(self):
        source='if a:\n    if b:\n        print(1)\n    else:\n        print(2)\n'
        self.assertEqual(validation_transform(source),source)

    def test_not_single_nested(self):
        source='if a:\n    print(1)\n'
        self.assertEqual(validation_transform(source),source)

    def test_not_calls(self):
        source='if f():\n    if b:\n        print(1)\n'
        self.assertEqual(validation_transform(source),source)

    def test_multi_body_outer_skip(self):
        source='if a:\n    if b:\n        print(1)\n    print(2)\n'
        self.assertEqual(validation_transform(source),source)

    def test_dynamic_skip(self):
        source='def f(a,b):\n    locals()\n    if a:\n        if b:\n            print(1)\n'
        self.assertEqual(validation_transform(source),source)

    def test_invalid_skip(self):
        self.assertEqual(validation_transform('if:'),'if:')


class BuiltinTransformTests(SharedAssertions):
    def test_basic_augassign(self):
        code='values=[1,2,3]\ntotal=0\nfor item in values:\n    total+=item\nresult=total\nprint(result)\n'
        out=self.changed_and_equivalent(builtin_transform,code)
        self.assertIn('total = sum(values)',out)

    def test_additional_explicit_assign(self):
        code='values=(3,4)\ntotal=0\nfor item in values:\n    total=total+item\nresult=total\nprint(result)\n'
        self.changed_and_equivalent(builtin_transform,code)

    def test_complex_predicate_in_function(self):
        code='def count_good(nums):\n    total=0\n    for n in nums:\n        if n>0:\n            total+=n\n    return total\nresult=count_good([-1,3,4])\nprint(result)\n'
        out=self.changed_and_equivalent(builtin_transform,code)
        self.assertIn('sum((n for n in nums if n>0))',out)

    def test_list_literal_iterable(self):
        code='total=0\nfor x in [1,2,3]:\n    total+=x\nresult=total\nprint(result)\n'
        self.changed_and_equivalent(builtin_transform,code)

    def test_no_loop_variable_use_after(self):
        code='total=0\nfor x in [1,2]:\n    total+=x\nprint(x)\n'
        self.assertEqual(builtin_transform(code),code)

    def test_skip_closure_referring_to_loop_target(self):
        code=('values=[1,2]\n'
              'def read_item():\n    return x\n'
              'total=0\nfor x in values:\n    total+=x\n'
              'result=read_item()\n')
        self.assertEqual(builtin_transform(code), code)

    def test_skip_shadowed_sum(self):
        code='sum=lambda seq:0\ntotal=0\nfor x in [1,2]:\n    total+=x\n'
        self.assertEqual(builtin_transform(code),code)

    def test_comment_skip(self):
        code='total=0\nfor x in [1,2]:\n    total+=x # explain\n'
        self.assertEqual(builtin_transform(code),code)

    def test_not_reassigned_iterable(self):
        code='total=0\nfor x in values:\n    x=2\n    total+=x\n'
        self.assertEqual(builtin_transform(code),code)

    def test_nonzero_initial(self):
        code='total=10\nfor x in values:\n    total+=x\n'
        self.assertEqual(builtin_transform(code),code)

    def test_no_global(self):
        code='def f(values):\n    global total\n    total=0\n    for x in values:\n        total+=x\n'
        self.assertEqual(builtin_transform(code),code)

    def test_crlf_unicode(self):
        code='값=[1,2]\r\n합계=0\r\nfor x in 값:\r\n    합계+=x\r\nresult=합계\r\nprint(result)\r\n'
        out=self.changed_and_equivalent(builtin_transform,code)
        self.assertNotIn('\n',out.replace('\r\n',''))

    def test_invalid_noop(self):
        self.assertEqual(builtin_transform('if:'),'if:')


# Installed application tests. Skipped only in intentionally incomplete sandbox.
try:
    from app.services.style_tag_transform_map_service import (
        CREATE_ACTION_BY_TAG, get_tag_transform_status,
    )
    from app.services.style_apply_service import _get_transform_function
    from app.services.style_diff_service import compare_style_with_target_code
    from app.services.style_transform_plan_service import build_transform_plan
    _INTEGRATION = True
except ImportError:
    _INTEGRATION = False


@unittest.skipUnless(_INTEGRATION, 'requires full capstone backend installation')
class ServiceIntegrationTests(unittest.TestCase):
    TAG_ACTIONS = {
        '데이터 변환 구조': 'create_safe_data_comprehension',
        '내장 함수 활용 구조': 'create_safe_builtin_sum',
        '검증 로직 중심 구조': 'create_safe_validation_condition',
    }

    def test_three_public_mappings_registered(self):
        for tag, action in self.TAG_ACTIONS.items():
            self.assertEqual(CREATE_ACTION_BY_TAG[tag], action)

    def test_three_dispatchers_callable(self):
        for action in self.TAG_ACTIONS.values():
            self.assertTrue(callable(_get_transform_function(action)))

    def test_linked_status_for_three_tags(self):
        for tag in self.TAG_ACTIONS:
            self.assertEqual(get_tag_transform_status(tag), 'linked')

    def _actions(self, tag, code, *, other_style_tags=()):
        style = {
            'syntax_tags': [],
            'concept_tags': [{'tag': name} for name in (tag, *other_style_tags)],
            'metrics': {},
        }
        diff = compare_style_with_target_code(style, code)
        return {row['action'] for row in build_transform_plan(diff)['actions']}

    def test_plan_data_transform(self):
        actions = self._actions('데이터 변환 구조',
                                'data=[-3,2]\nresult=list(map(abs,data))\n')
        self.assertIn('create_safe_data_comprehension', actions)

    def test_plan_builtin_sum(self):
        actions = self._actions('내장 함수 활용 구조',
                                'values=[1,2]\ntotal=0\nfor x in values:\n    total+=x\n')
        self.assertIn('create_safe_builtin_sum', actions)

    def test_plan_validation_condition(self):
        actions = self._actions('검증 로직 중심 구조',
                                'a=b=True\nif a:\n    if b:\n        print(1)\n')
        self.assertIn('create_safe_validation_condition', actions)

    def test_nested_preference_blocks_collapse(self):
        actions = self._actions('검증 로직 중심 구조',
                                'a=b=True\nif a:\n    if b:\n        print(1)\n',
                                other_style_tags=('조건문 중첩 구조',))
        self.assertNotIn('create_safe_validation_condition', actions)

    def test_state_update_preference_blocks_sum(self):
        actions = self._actions('내장 함수 활용 구조',
                                'values=[1,2]\ntotal=0\nfor x in values:\n    total+=x\n',
                                other_style_tags=('상태 변경 중심 구조',))
        self.assertNotIn('create_safe_builtin_sum', actions)
