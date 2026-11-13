"""Regression tests for conservative structural style transformations."""
import ast
import contextlib
import io
import unittest

from app.services.improvement.safe_structural_patterns_service import (
    transform_suppress_to_try as to_try,
    transform_try_to_suppress as to_suppress,
    transform_positional_to_keyword_call as to_keywords,
    transform_keyword_to_positional_call as to_positional,
    transform_getattr_to_attribute as to_attribute,
    transform_attribute_to_getattr as to_getattr,
)
from app.services.style_tag_transform_map_service import (
    CREATE_ACTION_BY_TAG, PLANNED_TAG_FAMILY, get_tag_transform_status,
)
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_apply_service import _get_transform_function, apply_coding_style


def _observe(code):
    values = {}
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        try:
            exec(compile(code, '<batch2>', 'exec'), values)
            error = None
        except Exception as exc:
            error = (type(exc).__name__, str(exc))
    selected = {k: values[k] for k in ('result', 'output', 'value') if k in values}
    return buffer.getvalue(), error, selected


def equivalent(testcase, source, transformer, marker=None):
    output = transformer(source)
    ast.parse(output)
    testcase.assertNotEqual(source, output)
    testcase.assertEqual(_observe(source), _observe(output))
    if marker:
        testcase.assertIn(marker, output)
    return output


def diff(*, missing_syntax=(), missing_concept=(), style_syntax=(), target_syntax=()):
    return {'missing_syntax_tags': [{'tag': k} for k in missing_syntax],
            'missing_concept_tags': [{'tag': k} for k in missing_concept],
            'style_syntax_names': set(style_syntax), 'target_syntax_names': set(target_syntax),
            'style_concept_names': set(), 'target_concept_names': set(),
            'style_metrics': {}, 'target_analysis': {'metrics': {}}}


class ExceptionsTests(unittest.TestCase):
    def test_to_try_value_error(self):
        src='import contextlib\nwith contextlib.suppress(ValueError):\n    value = int("no")\nresult = 4\n'
        equivalent(self, src, to_try, 'except ValueError:')

    def test_to_try_no_exception(self):
        src='import contextlib\nwith contextlib.suppress(ValueError):\n    result = int("4")\n'
        equivalent(self, src, to_try)

    def test_to_suppress_value_error(self):
        src='import contextlib\ntry:\n    value = int("no")\nexcept ValueError:\n    pass\nresult = 4\n'
        equivalent(self, src, to_suppress, 'contextlib.suppress(ValueError)')

    def test_to_suppress_no_exception(self):
        src='import contextlib\ntry:\n    result = int("4")\nexcept ValueError:\n    pass\n'
        equivalent(self, src, to_suppress)

    def test_key_error(self):
        src='import contextlib\nwith contextlib.suppress(KeyError):\n    value = {"a":1}["b"]\nresult = 3\n'
        equivalent(self, src, to_try)

    def test_zero_division(self):
        src='import contextlib\ntry:\n    value = 1 / 0\nexcept ZeroDivisionError:\n    pass\nresult = 3\n'
        equivalent(self, src, to_suppress)

    def test_roundtrip(self):
        src='import contextlib\nwith contextlib.suppress(ValueError):\n    print(int("x"))\n'
        mid=to_try(src)
        self.assertNotEqual(src,mid)
        self.assertEqual(_observe(src),_observe(to_suppress(mid)))

    def test_skip_import_after_with(self):
        src='with contextlib.suppress(ValueError):\n    print(1)\nimport contextlib\n'
        self.assertEqual(to_try(src), src)

    def test_skip_import_after_try(self):
        src='try:\n    print(1)\nexcept ValueError:\n    pass\nimport contextlib\n'
        self.assertEqual(to_suppress(src), src)

    def test_skip_no_contextlib_import(self):
        src='with contextlib.suppress(ValueError):\n    print(1)\n'
        self.assertEqual(to_try(src),src)

    def test_skip_alias(self):
        src='import contextlib as ctx\nwith ctx.suppress(ValueError):\n    print(1)\n'
        self.assertEqual(to_try(src),src)

    def test_skip_multimanager(self):
        src='import contextlib\nwith contextlib.suppress(ValueError), contextlib.suppress(KeyError):\n    print(1)\n'
        self.assertEqual(to_try(src),src)

    def test_skip_broad_except(self):
        src='import contextlib\ntry:\n    print(1)\nexcept Exception:\n    pass\n'
        self.assertEqual(to_suppress(src),src)

    def test_skip_nonpass_except(self):
        src='import contextlib\ntry:\n    print(1)\nexcept ValueError:\n    print(2)\n'
        self.assertEqual(to_suppress(src),src)

    def test_skip_else(self):
        src='import contextlib\ntry:\n    print(1)\nexcept ValueError:\n    pass\nelse:\n    print(2)\n'
        self.assertEqual(to_suppress(src),src)

    def test_skip_finally(self):
        src='import contextlib\ntry:\n    print(1)\nexcept ValueError:\n    pass\nfinally:\n    print(2)\n'
        self.assertEqual(to_suppress(src),src)

    def test_skip_shadowed_exception(self):
        src='import contextlib\nValueError = RuntimeError\nwith contextlib.suppress(ValueError):\n    print(1)\n'
        self.assertEqual(to_try(src),src)

    def test_skip_shadowed_module(self):
        src='import contextlib\ncontextlib = 3\nwith contextlib.suppress(ValueError):\n    print(1)\n'
        self.assertEqual(to_try(src),src)

    def test_skip_comments_inside(self):
        src='import contextlib\nwith contextlib.suppress(ValueError):\n    # important\n    print(1)\n'
        self.assertEqual(to_try(src),src)

    def test_skip_inline_comment(self):
        src='import contextlib\nwith contextlib.suppress(ValueError): # user comment\n    print(1)\n'
        self.assertEqual(to_try(src),src)

    def test_preserve_surrounding_comments(self):
        src='# before\nimport contextlib\nwith contextlib.suppress(ValueError):\n    print(1)\n# after\n'
        output=equivalent(self,src,to_try)
        self.assertIn('# before', output)
        self.assertIn('# after', output)

    def test_idempotent(self):
        src='import contextlib\nwith contextlib.suppress(ValueError):\n    print(1)\n'
        mid=to_try(src)
        self.assertEqual(to_try(mid),mid)


class ParameterTests(unittest.TestCase):
    def test_forward(self):
        src='def add(a, b):\n    return a+b\nresult=add(2,3)\n'
        equivalent(self,src,to_keywords,'add(a=2, b=3)')

    def test_reverse(self):
        src='def add(a, b):\n    return a+b\nresult=add(a=2,b=3)\n'
        equivalent(self,src,to_positional,'add(2, 3)')

    def test_three_parameters(self):
        src='def join(a,b,c):\n    return a+b+c\nresult=join("a","b","c")\n'
        equivalent(self,src,to_keywords)

    def test_two_calls(self):
        src='def add(a,b):\n    return a+b\nprint(add(1,2))\nresult=add(3,4)\n'
        output=to_keywords(src)
        self.assertIn('result = add(a=3, b=4)', output)
        self.assertEqual(_observe(src),_observe(output))

    def test_roundtrip(self):
        src='def add(a,b):\n    return a+b\nresult=add(2,3)\n'
        transformed=to_positional(to_keywords(src))
        self.assertEqual(_observe(src),_observe(transformed))

    def test_skip_signature_default(self):
        src='def f(a,b=2):\n    return a+b\nresult=f(1,3)\n'
        self.assertEqual(to_keywords(src),src)

    def test_skip_positional_only(self):
        src='def f(a,/,b):\n    return a+b\nresult=f(1,3)\n'
        self.assertEqual(to_keywords(src),src)

    def test_skip_varargs(self):
        src='def f(*a):\n    return sum(a)\nresult=f(1,3)\n'
        self.assertEqual(to_keywords(src),src)

    def test_skip_decorated(self):
        src='def deco(f):\n    return f\n@deco\ndef f(a):\n    return a\nresult=f(1)\n'
        self.assertEqual(to_keywords(src),src)

    def test_skip_before_function_def(self):
        src='result=f(1)\ndef f(a):\n    return a\n'
        self.assertEqual(to_keywords(src),src)

    def test_skip_reassigned(self):
        src='def f(a):\n    return a\nf=lambda a:2\nresult=f(1)\n'
        self.assertEqual(to_keywords(src),src)

    def test_skip_function_alias(self):
        src='def f(a):\n    return a\ng=f\nresult=f(1)\n'
        self.assertEqual(to_keywords(src),src)

    def test_skip_existing_keywords(self):
        src='def f(a,b):\n    return a+b\nresult=f(a=2,b=3)\n'
        self.assertEqual(to_keywords(src),src)

    def test_skip_keyword_reorder(self):
        src='def f(a,b):\n    return a+b\nresult=f(b=3,a=2)\n'
        self.assertEqual(to_positional(src),src)

    def test_skip_unpacked(self):
        src='def f(a,b):\n    return a+b\nresult=f(*(1,2))\n'
        self.assertEqual(to_keywords(src),src)

    def test_skip_comments(self):
        src='def f(a):\n    return a\nresult=f(1) # important\n'
        self.assertEqual(to_keywords(src),src)

    def test_unicode(self):
        src='def 합계(값,배수):\n    return 값*배수\nresult=합계(4,5)\n'
        equivalent(self,src,to_keywords,'합계(값=4, 배수=5)')

    def test_skip_introspection(self):
        src='def f(a):\n    return a\nresult=f(2)\nprint(locals())\n'
        self.assertEqual(to_keywords(src),src)

    def test_skip_invalid_code(self):
        src='def broken(\n'
        self.assertEqual(to_keywords(src),src)

    def test_idempotent(self):
        src='def f(a):\n    return a\nresult=f(2)\n'
        mid=to_keywords(src)
        self.assertEqual(to_keywords(mid),mid)


class AttributeTests(unittest.TestCase):
    PREFIX='class Item:\n    def __init__(self):\n        self.color="red"\nobj=Item()\n'

    def test_getattr_forward(self):
        src=self.PREFIX+'result=getattr(obj,"color")\n'
        equivalent(self,src,to_attribute,'obj.color')

    def test_getattr_reverse(self):
        src=self.PREFIX+'result=obj.color\n'
        equivalent(self,src,to_getattr,"getattr(obj, 'color')")

    def test_missing_attribute_raises_same(self):
        src=self.PREFIX+'result=getattr(obj,"unknown")\n'
        equivalent(self,src,to_attribute)

    def test_property(self):
        src='class Item:\n    @property\n    def color(self):\n        print("read")\n        return "red"\nobj=Item()\nresult=getattr(obj,"color")\n'
        equivalent(self,src,to_attribute)

    def test_multiple_access(self):
        src=self.PREFIX+'result=getattr(obj,"color")\noutput=getattr(obj,"color")\n'
        equivalent(self,src,to_attribute)

    def test_unicode_attribute(self):
        src='class Box:\n    색상="파랑"\nobj=Box()\nresult=getattr(obj,"색상")\n'
        equivalent(self,src,to_attribute,'obj.색상')

    def test_skip_default_getattr(self):
        src=self.PREFIX+'result=getattr(obj,"missing",None)\n'
        self.assertEqual(to_attribute(src),src)

    def test_skip_shadowed_getattr(self):
        src='getattr = lambda a,b: 3\n'+self.PREFIX+'result=getattr(obj,"color")\n'
        self.assertEqual(to_attribute(src),src)

    def test_skip_dunder(self):
        src=self.PREFIX+'result=getattr(obj,"__dict__")\n'
        self.assertEqual(to_attribute(src),src)

    def test_skip_invalid_attr_name(self):
        src=self.PREFIX+'result=getattr(obj,"has space")\n'
        self.assertEqual(to_attribute(src),src)

    def test_skip_nested_object(self):
        src='result=getattr(make(),"color")\n'
        self.assertEqual(to_attribute(src),src)

    def test_skip_assignment_to_attr(self):
        src=self.PREFIX+'obj.color="green"\n'
        self.assertEqual(to_getattr(src),src)

    def test_skip_comment_inline(self):
        src=self.PREFIX+'result=getattr(obj,"color") # keep\n'
        self.assertEqual(to_attribute(src),src)

    def test_skip_class_scope(self):
        src='class Item:\n    result = getattr(obj,"color")\n'
        self.assertEqual(to_attribute(src),src)

    def test_idempotent(self):
        src=self.PREFIX+'result=getattr(obj,"color")\n'
        mid=to_attribute(src)
        self.assertEqual(to_attribute(mid),mid)


class RegistryTests(unittest.TestCase):
    def test_public_actions(self):
        expected={'예외 처리':'create_safe_explicit_exception',
                  '예외 처리 포함 구조':'create_safe_explicit_exception',
                  '함수 매개변수 활용 구조':'create_safe_keyword_call',
                  '객체 접근 중심 구조':'create_safe_direct_attribute'}
        for tag,action in expected.items():
            with self.subTest(tag=tag):
                self.assertEqual(CREATE_ACTION_BY_TAG[tag],action)
                self.assertNotIn(tag,PLANNED_TAG_FAMILY)
                self.assertEqual(get_tag_transform_status(tag),'linked')
                self.assertTrue(callable(_get_transform_function(action)))

    def test_internal_reverse_actions(self):
        for action in ['create_safe_exception_suppress','create_safe_positional_call','create_safe_getattr_call']:
            self.assertTrue(callable(_get_transform_function(action)))

    def test_missing_exception_tag_selects_one_action(self):
        plan=build_transform_plan(diff(missing_syntax=['예외 처리'],missing_concept=['예외 처리 포함 구조']))
        self.assertEqual([a['action'] for a in plan['actions']], ['create_safe_explicit_exception'])

    def test_missing_parameter_tag(self):
        plan=build_transform_plan(diff(missing_concept=['함수 매개변수 활용 구조']))
        self.assertEqual([a['action'] for a in plan['actions']], ['create_safe_keyword_call'])

    def test_missing_attribute_tag(self):
        plan=build_transform_plan(diff(missing_concept=['객체 접근 중심 구조']))
        self.assertEqual([a['action'] for a in plan['actions']], ['create_safe_direct_attribute'])

    def test_legacy_actions_preserved(self):
        for action in ['create_safe_set_comprehension','create_safe_lambda_expression',
                       'create_safe_pattern_matching','create_safe_local_annotation',
                       'create_direct_iteration','create_safe_dict_comprehension']:
            self.assertIsNotNone(_get_transform_function(action))

    def test_exception_and_sort_coexist(self):
        plan=build_transform_plan(diff(missing_syntax=['예외 처리'],missing_concept=['정렬 중심 구조']))
        self.assertEqual({a['action'] for a in plan['actions']},
                         {'create_safe_explicit_exception','create_sort_style'})


class EndToEndTests(unittest.TestCase):
    def _apply(self, code, missing_syntax=(), missing_concept=()):
        from unittest.mock import patch
        from app.services import style_apply_service as app
        with patch.object(app, 'compare_style_with_target_code', return_value=diff(
                missing_syntax=missing_syntax, missing_concept=missing_concept)), \
             patch.object(app, 'compare_after_transform', return_value={
                'missing_syntax_tags': [], 'missing_concept_tags': []}), \
             patch.object(app, 'verify_execution_equivalence', return_value={
                'status': 'equivalent', 'equivalent': True,
                'message': 'controlled test', 'function_verification': None}):
            return app.apply_coding_style(code, {})

    def test_exception_style_dispatch(self):
        src='import contextlib\nwith contextlib.suppress(ValueError):\n    value=int("no")\n'
        code,*rest=self._apply(src,missing_syntax=('예외 처리',))
        self.assertIn('except ValueError:',code)
        self.assertEqual(_observe(src),_observe(code))

    def test_parameter_style_dispatch(self):
        src='def add(a,b):\n    return a+b\nresult=add(2,3)\n'
        code,*rest=self._apply(src,missing_concept=('함수 매개변수 활용 구조',))
        self.assertIn('add(a=2, b=3)',code)
        self.assertEqual(_observe(src),_observe(code))

    def test_attribute_style_dispatch(self):
        src='class Obj:\n    color="red"\nobj=Obj()\nresult=getattr(obj,"color")\n'
        code,*rest=self._apply(src,missing_concept=('객체 접근 중심 구조',))
        self.assertIn('obj.color',code)
        self.assertEqual(_observe(src),_observe(code))


if __name__ == '__main__':
    unittest.main()
