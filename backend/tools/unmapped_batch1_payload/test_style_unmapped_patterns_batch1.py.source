"""Regression tests for first formerly compare-only tag transform batch.

Only trusted static fixtures are executed; this module does not run user input.
"""
import ast
import unittest
import importlib.util

from app.services.improvement.safe_unmapped_patterns_service import (
    transform_to_nested_conditions as nested,
    transform_to_deep_conditions as deep,
    transform_to_literal_collections as literal,
    transform_to_multiple_returns as returns,
)


def output(code: str):
    import contextlib
    import io
    buf = io.StringIO()
    ns = {}
    with contextlib.redirect_stdout(buf):
        exec(compile(code, '<fixed-trusted-fixture>', 'exec'), ns)
    return buf.getvalue()


class NestedConditionTests(unittest.TestCase):
    def assert_same(self, before):
        after = nested(before)
        self.assertNotEqual(after, before)
        ast.parse(after)
        self.assertEqual(output(before), output(after))
        self.assertEqual(nested(after), after)
        return after

    def test_basic_two_conditions(self):
        after = self.assert_same('a=True\nb=True\nif a and b:\n    print("yes")\n')
        self.assertIn('if a:\n    if b:', after)

    def test_additional_three_conditions(self):
        after = self.assert_same('a=True\nb=True\nc=True\nif a and b and c:\n    print("yes")\n')
        self.assertIn('        if c:', after)

    def test_complex_in_function(self):
        before = 'def run(a,b,c):\n    if a and b and c:\n        if c:\n            return 7\n    return 0\nprint(run(True,True,True))\n'
        after = self.assert_same(before)
        self.assertIn('            if c:', after)

    def test_four_terms(self):
        self.assert_same('a=b=c=d=True\nif a and b and c and d:\n    print(4)\n')

    def test_comparison_conditions(self):
        self.assert_same('a=1\nb=2\nif a > 0 and b < 3:\n    print("yes")\n')

    def test_false_branches_no_output(self):
        self.assert_same('a=True\nb=False\nif a and b:\n    print("x")\nprint("done")\n')

    def test_code_before_after_preserved(self):
        before = '# prefix\na=True\nb=True\nif a and b:\n    print(1)\n# suffix\nprint(2)\n'
        after = nested(before)
        self.assertTrue(after.startswith('# prefix\n'))
        self.assertTrue(after.endswith('# suffix\nprint(2)\n'))
        self.assertEqual(output(before), output(after))

    def test_else_rejected(self):
        before = 'if a and b:\n    print(1)\nelse:\n    print(2)\n'
        self.assertEqual(nested(before), before)

    def test_elif_rejected(self):
        before = 'if a and b:\n    print(1)\nelif c:\n    print(2)\n'
        self.assertEqual(nested(before), before)

    def test_inline_rejected(self):
        before = 'if a and b: print(1)\n'
        self.assertEqual(nested(before), before)

    def test_comment_protected(self):
        before = 'if a and b:\n    # preserve\n    print(1)\n'
        self.assertEqual(nested(before), before)

    def test_call_condition_rejected(self):
        before = 'if a() and b:\n    print(1)\n'
        self.assertEqual(nested(before), before)

    def test_unsafe_dynamic_rejected(self):
        before = 'def f(a,b):\n    locals()\n    if a and b:\n        return 5\n'
        self.assertEqual(nested(before), before)

    def test_unicode_crlf(self):
        before = '값=True\r\n참=True\r\nif 값 and 참:\r\n    print("가나다")\r\n'
        after = self.assert_same(before)
        self.assertTrue('\r\n' in after)
        self.assertNotIn('\n', after.replace('\r\n',''))

    def test_invalid_code_noop(self):
        self.assertEqual(nested('if :'), 'if :')


class DeepConditionTests(unittest.TestCase):
    def test_three_terms_deep(self):
        before = 'a=b=c=True\nif a and b and c:\n    print(4)\n'
        after = deep(before)
        self.assertIn('        if c:', after)
        self.assertEqual(output(before), output(after))

    def test_four_terms_deep(self):
        before = 'a=b=c=d=True\nif a and b and c and d:\n    print(4)\n'
        after = deep(before)
        self.assertIn('            if d:', after)
        self.assertEqual(output(before), output(after))

    def test_in_function(self):
        before = 'def f(a,b,c):\n    if a and b and c:\n        return 1\n    return 0\nprint(f(True,True,False))\n'
        after = deep(before)
        self.assertIn('            if c:', after)
        self.assertEqual(output(before), output(after))

    def test_two_terms_left_unchanged(self):
        before = 'if a and b:\n    print(1)\n'
        self.assertEqual(deep(before), before)


class CollectionLiteralTests(unittest.TestCase):
    def assert_same(self, before):
        after = literal(before)
        self.assertNotEqual(after, before)
        ast.parse(after)
        self.assertEqual(output(before), output(after))
        self.assertEqual(literal(after), after)
        return after

    def test_basic_list(self):
        self.assertIn('data = []', self.assert_same('data = list()\nprint(data)\n'))

    def test_additional_dict(self):
        self.assertIn('data = {}', self.assert_same('data = dict()\nprint(data)\n'))

    def test_complex_tuple(self):
        self.assertIn('data = ()', self.assert_same('data = tuple()\nprint(data)\n'))

    def test_all_three_mixed(self):
        after = self.assert_same('a=list(); b=dict(); c=tuple()\nprint(a,b,c)\n')
        self.assertIn('a=[]; b={}; c=()', after)

    def test_multiple_functions(self):
        before = 'def f():\n    return list()\ndef g():\n    return dict()\nprint(f(),g())\n'
        self.assert_same(before)

    def test_unicode_source(self):
        before = '한글 = list()\nprint(한글)\n'
        self.assert_same(before)

    def test_shadowed_name_rejected(self):
        before = 'list=lambda: [99]\nvalue=list()\nprint(value)\n'
        self.assertEqual(literal(before), before)

    def test_function_parameter_shadowed(self):
        before = 'def f(list):\n    return list()\n'
        self.assertEqual(literal(before), before)

    def test_shadowed_dict_only_reject_dict(self):
        before = 'dict=lambda: {"z":2}\na=dict()\nb=list()\nprint(a,b)\n'
        after = literal(before)
        self.assertIn('a=dict()', after)
        self.assertIn('b=[]', after)
        self.assertEqual(output(before), output(after))

    def test_nonempty_call_rejected(self):
        before = 'print(list(range(3)))\n'
        self.assertEqual(literal(before), before)

    def test_dynamic_name_rejected(self):
        before = 'print(globals())\na=list()\n'
        self.assertEqual(literal(before), before)

    def test_comment_on_call_line_preserved(self):
        before = 'x=list() # comment\n'
        self.assertEqual(literal(before), before)

    def test_invalid_code_noop(self):
        self.assertEqual(literal('def :'), 'def :')


class MultipleReturnsTests(unittest.TestCase):
    def assert_same(self, before):
        after = returns(before)
        self.assertNotEqual(after, before)
        ast.parse(after)
        self.assertEqual(output(before), output(after))
        self.assertEqual(returns(after), after)
        return after

    def test_basic_initial_default(self):
        before = 'def f(x):\n    result=0\n    if x>0:\n        result=1\n    return result\nprint(f(2),f(-1))\n'
        after = self.assert_same(before)
        self.assertIn('return 1', after)
        self.assertIn('return 0', after)

    def test_additional_if_else(self):
        before = 'def f(flag,a,b):\n    if flag:\n        result=a\n    else:\n        result=b\n    return result\nprint(f(True,2,3), f(False,2,3))\n'
        self.assert_same(before)

    def test_complex_ternary(self):
        before = 'def f(flag,a,b):\n    result = a if flag else b\n    return result\nprint(f(True,2,3), f(False,2,3))\n'
        after = self.assert_same(before)
        self.assertIn('if flag:', after)

    def test_two_functions(self):
        before = 'def f(x):\n    result=0\n    if x:\n        result=1\n    return result\ndef g(x):\n    result=2 if x else 3\n    return result\nprint(f(True),g(False))\n'
        self.assert_same(before)

    def test_no_result_variable(self):
        before = 'def f(x):\n    if x:\n        return 1\n    return 0\n'
        self.assertEqual(returns(before), before)

    def test_nontrailing_rejected(self):
        before = 'def f(x):\n    result=1 if x else 2\n    print("intermediate")\n    return result\n'
        self.assertEqual(returns(before), before)

    def test_comment_inside_rejected(self):
        before = 'def f(x):\n    result=1 if x else 2 # comment\n    return result\n'
        self.assertEqual(returns(before), before)

    def test_name_depends_on_assigned_result_rejected(self):
        before = 'def f(result):\n    result = 3\n    if result > 1:\n        result = 2\n    return result\n'
        self.assertEqual(returns(before), before)

    def test_calls_in_result_rejected(self):
        before = 'def f(x):\n    result=x+1 if x else 2\n    return result\n'
        self.assertEqual(returns(before), before)

    def test_locals_rejected(self):
        before = 'def f(x):\n    locals()\n    result=1 if x else 2\n    return result\n'
        self.assertEqual(returns(before), before)

    def test_decorator_rejected(self):
        before = '@dec\ndef f(x):\n    result=1 if x else 2\n    return result\n'
        self.assertEqual(returns(before), before)

    def test_unicode(self):
        before = 'def f(x):\n    결과=1 if x else 2\n    return 결과\nprint(f(True))\n'
        self.assert_same(before)

    def test_invalid_code_noop(self):
        self.assertEqual(returns('def :'), 'def :')


@unittest.skipUnless(importlib.util.find_spec("app.services.style_tag_transform_map_service") is not None, "integration requires complete backend")
class DispatchIntegrationTests(unittest.TestCase):
    def test_four_tag_mappings_if_app_available(self):
        from app.services.style_tag_transform_map_service import get_create_action_for_tag
        self.assertEqual(get_create_action_for_tag('조건문 중첩 구조'), 'create_safe_nested_conditions')
        self.assertEqual(get_create_action_for_tag('깊은 중첩 구조'), 'create_safe_deep_conditions')
        self.assertEqual(get_create_action_for_tag('데이터 컬렉션 중심 구조'), 'create_safe_collection_literals')
        self.assertEqual(get_create_action_for_tag('반환 중심 구조'), 'create_safe_multiple_returns')

    def test_plans_if_app_available(self):
        from app.services.style_transform_plan_service import build_transform_plan
        for tag in ('조건문 중첩 구조','깊은 중첩 구조','데이터 컬렉션 중심 구조','반환 중심 구조'):
            plan=build_transform_plan({'missing_concept_tags':[{'tag':tag}]})
            self.assertTrue(any(item['tag']==tag for item in plan['actions']), tag)

    def test_dispatchers_if_app_available(self):
        from app.services.style_apply_service import _get_transform_function
        for action in ('create_safe_nested_conditions','create_safe_deep_conditions','create_safe_collection_literals','create_safe_multiple_returns'):
            self.assertTrue(callable(_get_transform_function(action)), action)


@unittest.skipUnless(importlib.util.find_spec("app.services.style_apply_service") is not None,
                     "integration requires complete backend")
class EndToEndApplyTests(unittest.TestCase):
    def apply(self, tag, code, expected_fragment):
        from app.services.style_apply_service import apply_coding_style
        style = {
            "id": "batch1-fixed", "name": "fixture", "description": "",
            "syntax_tags": [], "concept_tags": [{"tag": tag}],
            "metrics": {}, "created_at": "fixture", "formatting_style": None,
        }
        transformed, summary, rules, warnings, diff, verification = apply_coding_style(code, style)
        self.assertIn(expected_fragment, transformed)
        self.assertNotEqual(transformed, code)
        self.assertEqual(verification["status"], "equivalent", warnings)
        self.assertTrue(any('적용 완료' in row for row in rules), summary)

    def test_nested_tag_real_pipeline(self):
        self.apply('조건문 중첩 구조',
                   'a=True\nb=True\nif a and b:\n    print(4)\n',
                   'if a:\n    if b:')

    def test_deep_tag_real_pipeline(self):
        self.apply('깊은 중첩 구조',
                   'a=b=c=True\nif a and b and c:\n    print(4)\n',
                   '        if c:')

    def test_collection_tag_real_pipeline(self):
        self.apply('데이터 컬렉션 중심 구조',
                   'a=list()\nb=list()\nprint(a,b)\n',
                   'a=[]')

    def test_return_tag_real_pipeline(self):
        self.apply('반환 중심 구조',
                   'def f(flag):\n    result=0\n    if flag:\n        result=1\n    return result\nprint(f(True))\n',
                   'return 1')


if __name__ == '__main__':
    unittest.main()
