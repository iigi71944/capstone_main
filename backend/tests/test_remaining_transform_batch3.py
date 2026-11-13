"""Conservative method decorator, guard and operator style conversion tests."""
import ast
import contextlib
import io
import unittest
from unittest.mock import patch

from app.services.improvement.safe_remaining_patterns_service import (
    transform_assignment_to_decorator as make_decorator,
    transform_decorator_to_assignment as make_assignment,
    transform_next_default_to_try as make_guard,
    transform_try_to_next_default as make_next,
    transform_arithmetic_to_operator_call as make_call,
    transform_operator_call_to_arithmetic as make_expression,
)
from app.services.style_tag_transform_map_service import (
    CREATE_ACTION_BY_TAG, PLANNED_TAG_FAMILY, get_tag_transform_status,
)
from app.services.style_apply_service import _get_transform_function, apply_coding_style
from app.services.style_transform_plan_service import build_transform_plan


def observed(text):
    buf = io.StringIO()
    namespace = {}
    with contextlib.redirect_stdout(buf):
        try:
            exec(compile(text, '<batch3>', 'exec'), namespace)
            error = None
        except Exception as exc:
            error = (type(exc).__name__, str(exc))
    return (buf.getvalue(), error, {k: namespace[k] for k in ('result', 'value', 'output') if k in namespace})


def equivalent(case, src, func, marker=None):
    output = func(src)
    ast.parse(output)
    case.assertNotEqual(src, output)
    case.assertEqual(observed(src), observed(output))
    if marker:
        case.assertIn(marker, output)
    return output


def diff(missing_syntax=(), missing_concept=(), style_syntax=(), target_syntax=()):
    return {
        'missing_syntax_tags': [{'tag': tag} for tag in missing_syntax],
        'missing_concept_tags': [{'tag': tag} for tag in missing_concept],
        'style_syntax_names': set(style_syntax),
        'target_syntax_names': set(target_syntax),
        'style_concept_names': set(), 'target_concept_names': set(),
        'style_metrics': {}, 'target_analysis': {'metrics': {}},
    }


class DecoratorsTests(unittest.TestCase):
    SAMPLE = ('class A:\n    def f(x):\n        return x + 1\n'
              '    f = staticmethod(f)\nresult = A.f(2)\n')

    def test_staticmethod_forward(self):
        equivalent(self, self.SAMPLE, make_decorator, '@staticmethod')

    def test_staticmethod_reverse(self):
        equivalent(self, make_decorator(self.SAMPLE), make_assignment, 'f = staticmethod(f)')

    def test_classmethod_forward(self):
        s=('class A:\n    def label(cls):\n        return cls.__name__\n'
           '    label = classmethod(label)\nresult = A.label()\n')
        equivalent(self, s, make_decorator, '@classmethod')

    def test_classmethod_reverse(self):
        s='class A:\n    @classmethod\n    def label(cls):\n        return cls.__name__\nresult = A.label()\n'
        equivalent(self, s, make_assignment, 'label = classmethod(label)')

    def test_property_forward(self):
        s='class A:\n    def color(self):\n        return "blue"\n    color = property(color)\nresult = A().color\n'
        equivalent(self, s, make_decorator, '@property')

    def test_property_reverse(self):
        s='class A:\n    @property\n    def color(self):\n        return "blue"\nresult = A().color\n'
        equivalent(self, s, make_assignment, 'color = property(color)')

    def test_multimethods(self):
        s=('class A:\n    def left(x):\n        return x + 1\n    left = staticmethod(left)\n'
           '    def right(x):\n        return x * 2\n    right = staticmethod(right)\n'
           'result = A.left(2) + A.right(3)\n')
        out=equivalent(self,s,make_decorator)
        self.assertEqual(out.count('@staticmethod'),2)

    def test_nested_classes(self):
        s=('class Outer:\n    class Inner:\n        def value(x):\n            return x\n'
           '        value = staticmethod(value)\nresult = Outer.Inner.value(2)\n')
        equivalent(self,s,make_decorator,'@staticmethod')

    def test_surrounding_comments(self):
        s='# before\n'+self.SAMPLE+'# after\n'
        out=equivalent(self,s,make_decorator)
        self.assertIn('# before',out)
        self.assertIn('# after',out)

    def test_skip_comment_inside(self):
        s='class A:\n    def f(x):\n        # important\n        return x\n    f = staticmethod(f)\n'
        self.assertEqual(make_decorator(s),s)

    def test_skip_comment_between(self):
        s='class A:\n    def f(x):\n        return x\n    # important\n    f = staticmethod(f)\n'
        self.assertEqual(make_decorator(s),s)

    def test_skip_inline_comment(self):
        s='class A:\n    def f(x):\n        return x\n    f = staticmethod(f) # important\n'
        self.assertEqual(make_decorator(s),s)

    def test_skip_multiple_decorators(self):
        s='class A:\n    @staticmethod\n    @property\n    def value(self):\n        return 1\n'
        self.assertEqual(make_assignment(s),s)

    def test_skip_unrelated_wrapper(self):
        s='class A:\n    def f(x):\n        return x\n    f = fake_decorator(f)\n'
        self.assertEqual(make_decorator(s),s)

    def test_skip_nonclass(self):
        s='def f(x):\n    return x\nf = staticmethod(f)\n'
        self.assertEqual(make_decorator(s),s)

    def test_skip_introspection(self):
        s='print(locals())\n'+self.SAMPLE
        self.assertEqual(make_decorator(s),s)

    def test_idempotent(self):
        out=make_decorator(self.SAMPLE)
        self.assertEqual(make_decorator(out),out)

    def test_roundtrip(self):
        out=make_assignment(make_decorator(self.SAMPLE))
        self.assertEqual(observed(self.SAMPLE),observed(out))

    def test_unicode_names(self):
        s='class A:\n    def 색상(x):\n        return x\n    색상 = staticmethod(색상)\nresult=A.색상("red")\n'
        equivalent(self,s,make_decorator,'@staticmethod')


class GuardTests(unittest.TestCase):
    SRC='it = iter([])\nresult = next(it, "done")\n'

    def test_empty(self):
        equivalent(self, self.SRC, make_guard, 'except StopIteration:')

    def test_nonempty(self):
        s='it = iter([4])\nresult = next(it, 0)\n'
        equivalent(self,s,make_guard)

    def test_none(self):
        s='it = iter([])\nresult = next(it, None)\n'
        equivalent(self,s,make_guard)

    def test_bool(self):
        s='it = iter([])\nresult = next(it, False)\n'
        equivalent(self,s,make_guard)

    def test_reverse(self):
        equivalent(self,make_guard(self.SRC),make_next,'next(it,')

    def test_exception_noniterator(self):
        s='it = object()\nresult = next(it, "no")\n'
        equivalent(self,s,make_guard)

    def test_inside_function(self):
        s='def f():\n    it=iter([])\n    result=next(it, 0)\n    return result\nprint(f())\n'
        equivalent(self,s,make_guard,'except StopIteration:')

    def test_multiple_statements(self):
        s='a=iter([])\nb=iter([3])\nresult=next(a,0)\noutput=next(b,4)\n'
        out=equivalent(self,s,make_guard)
        self.assertEqual(out.count('except StopIteration:'),2)

    def test_unchanged_lookups(self):
        s='it=iter([])\nresult = next(it)\n'
        self.assertEqual(make_guard(s),s)

    def test_skip_keyword_default(self):
        s='it=iter([])\nresult=next(it, default=None)\n'
        self.assertEqual(make_guard(s),s)

    def test_skip_dynamic_default(self):
        s='it=iter([])\nx=2\nresult=next(it,x)\n'
        self.assertEqual(make_guard(s),s)

    def test_skip_next_shadowed(self):
        s='next=lambda it,default: default\nit=iter([])\nresult=next(it,1)\n'
        self.assertEqual(make_guard(s),s)

    def test_skip_stopiteration_shadowed(self):
        s='StopIteration = ValueError\nit=iter([])\nresult=next(it,1)\n'
        self.assertEqual(make_guard(s),s)

    def test_skip_except_extra(self):
        s='it=iter([])\ntry:\n    result=next(it)\nexcept StopIteration:\n    result=0\nfinally:\n    print("done")\n'
        self.assertEqual(make_next(s),s)

    def test_skip_except_inconsistent_target(self):
        s='it=iter([])\ntry:\n    result=next(it)\nexcept StopIteration:\n    other=0\n'
        self.assertEqual(make_next(s),s)

    def test_skip_comments(self):
        s='it=iter([])\nresult=next(it,0) # keep\n'
        self.assertEqual(make_guard(s),s)

    def test_skip_introspection(self):
        s='print(locals())\n'+self.SRC
        self.assertEqual(make_guard(s),s)

    def test_idempotent(self):
        out=make_guard(self.SRC)
        self.assertEqual(make_guard(out),out)

    def test_no_rewrite_class_body(self):
        s='class A:\n    it=iter([])\n    result=next(it,0)\n'
        self.assertEqual(make_guard(s),s)

    def test_roundtrip(self):
        out=make_next(make_guard(self.SRC))
        self.assertEqual(observed(self.SRC),observed(out))

    def test_unicode_value(self):
        s='it=iter([])\nresult=next(it,"완료")\n'
        equivalent(self,s,make_guard)


class OperatorTests(unittest.TestCase):
    SRC='import operator\na=2\nb=3\nresult=a+b\n'

    def test_add(self):
        equivalent(self,self.SRC,make_call,'operator.add(a, b)')

    def test_sub(self):
        s='import operator\na=8\nb=3\nresult=a-b\n'
        equivalent(self,s,make_call,'operator.sub(a, b)')

    def test_mul(self):
        s='import operator\na=2\nb=3\nresult=a*b\n'
        equivalent(self,s,make_call,'operator.mul(a, b)')

    def test_div(self):
        s='import operator\na=6\nb=3\nresult=a/b\n'
        equivalent(self,s,make_call,'operator.truediv(a, b)')

    def test_floor(self):
        s='import operator\na=7\nb=2\nresult=a//b\n'
        equivalent(self,s,make_call,'operator.floordiv(a, b)')

    def test_mod(self):
        s='import operator\na=7\nb=2\nresult=a%b\n'
        equivalent(self,s,make_call,'operator.mod(a, b)')

    def test_error_div_zero(self):
        s='import operator\na=3\nb=0\nresult=a/b\n'
        equivalent(self,s,make_call)

    def test_string_concat(self):
        s='import operator\na="hello"\nb="world"\nresult=a+b\n'
        equivalent(self,s,make_call)

    def test_reverse(self):
        equivalent(self,make_call(self.SRC),make_expression,'result = a + b')

    def test_multiple(self):
        s='import operator\na=2\nb=3\nresult=a+b\noutput=a*b\n'
        out=equivalent(self,s,make_call)
        self.assertIn('operator.mul',out)

    def test_import_after_expression(self):
        s='a=2\nb=3\nresult=a+b\nimport operator\n'
        self.assertEqual(make_call(s),s)

    def test_skip_no_import(self):
        s='a=2\nb=3\nresult=a+b\n'
        self.assertEqual(make_call(s),s)

    def test_skip_alias_import(self):
        s='import operator as op\na=2\nb=3\nresult=a+b\n'
        self.assertEqual(make_call(s),s)

    def test_skip_operator_rebinding(self):
        s='import operator\noperator=3\na=2\nb=3\nresult=a+b\n'
        self.assertEqual(make_call(s),s)

    def test_skip_operator_monkeypatch(self):
        s='import operator\noperator.add=lambda x,y:42\na=2\nb=3\nresult=a+b\n'
        self.assertEqual(make_call(s),s)

    def test_skip_complex_operand_call(self):
        s='import operator\ndef f():\n    return 1\nresult=f()+2\n'
        self.assertEqual(make_call(s),s)

    def test_skip_complex_operand_attr(self):
        s='import operator\nclass A:\n    value=3\nresult=A.value+2\n'
        self.assertEqual(make_call(s),s)

    def test_skip_semicolon(self):
        s='import operator\na=2\nb=3\nresult=a+b;print(result)\n'
        self.assertEqual(make_call(s),s)

    def test_skip_comment(self):
        s='import operator\na=2\nb=3\nresult=a+b # keep\n'
        self.assertEqual(make_call(s),s)

    def test_skip_namespace_access(self):
        s='import operator\nprint(globals())\na=2\nb=3\nresult=a+b\n'
        self.assertEqual(make_call(s),s)

    def test_idempotent(self):
        out=make_call(self.SRC)
        self.assertEqual(make_call(out),out)

    def test_roundtrip(self):
        self.assertEqual(observed(self.SRC),observed(make_expression(make_call(self.SRC))))

    def test_unicode_comment_preserved(self):
        s='# 한글\n'+self.SRC
        out=equivalent(self,s,make_call)
        self.assertIn('# 한글',out)


class StyleIntegrationTests(unittest.TestCase):
    EXPECTED = {'데코레이터 사용':'create_safe_method_decorator',
                '방어적 프로그래밍 구조':'create_safe_next_guard',
                '함수 호출 중심 구조':'create_safe_operator_call',
                '함수 정의':'create_safe_lambda_function'}

    def test_tag_map_connected(self):
        for tag, action in self.EXPECTED.items():
            with self.subTest(tag=tag):
                self.assertEqual(CREATE_ACTION_BY_TAG[tag],action)
                self.assertNotIn(tag,PLANNED_TAG_FAMILY)
                self.assertEqual(get_tag_transform_status(tag),'linked')

    def test_dispatchers(self):
        for action in self.EXPECTED.values():
            self.assertTrue(callable(_get_transform_function(action)))

    def test_reverse_dispatchers(self):
        for action in ('create_safe_method_decorator_assignment',
                       'create_safe_next_default', 'create_safe_arithmetic_expression'):
            self.assertTrue(callable(_get_transform_function(action)))

    def test_plan_decorator(self):
        self.assertEqual([x['action'] for x in build_transform_plan(diff(missing_syntax=['데코레이터 사용']))['actions']],
                         ['create_safe_method_decorator'])

    def test_plan_defensive(self):
        self.assertEqual([x['action'] for x in build_transform_plan(diff(missing_concept=['방어적 프로그래밍 구조']))['actions']],
                         ['create_safe_next_guard'])

    def test_plan_call(self):
        self.assertEqual([x['action'] for x in build_transform_plan(diff(missing_concept=['함수 호출 중심 구조']))['actions']],
                         ['create_safe_operator_call'])

    def test_plan_definition(self):
        self.assertEqual([x['action'] for x in build_transform_plan(diff(missing_syntax=['함수 정의']))['actions']],
                         ['create_safe_lambda_function'])

    def test_conflicting_lambda_preferences(self):
        actions=[x['action'] for x in build_transform_plan(diff(missing_syntax=['함수 정의','lambda식']))['actions']]
        self.assertNotIn('create_safe_lambda_function',actions)
        self.assertNotIn('create_safe_lambda_expression',actions)

    def _apply(self, source, missing_syntax=(), missing_concept=()):
        from app.services import style_apply_service as app
        with patch.object(app,'compare_style_with_target_code',return_value=diff(missing_syntax,missing_concept)),\
             patch.object(app,'compare_after_transform',return_value={'missing_syntax_tags': [], 'missing_concept_tags': []}),\
             patch.object(app,'verify_execution_equivalence',return_value={
                 'status':'equivalent','equivalent':True,'message':'controlled test','function_verification':None}):
            return apply_coding_style(source,{})

    def test_end_to_end_decorator(self):
        src=DecoratorsTests.SAMPLE
        output=self._apply(src,missing_syntax=['데코레이터 사용'])[0]
        self.assertIn('@staticmethod',output)
        self.assertEqual(observed(src),observed(output))

    def test_end_to_end_guard(self):
        output=self._apply(GuardTests.SRC,missing_concept=['방어적 프로그래밍 구조'])[0]
        self.assertIn('except StopIteration',output)
        self.assertEqual(observed(GuardTests.SRC),observed(output))

    def test_end_to_end_call(self):
        output=self._apply(OperatorTests.SRC,missing_concept=['함수 호출 중심 구조'])[0]
        self.assertIn('operator.add(',output)
        self.assertEqual(observed(OperatorTests.SRC),observed(output))

    def test_no_safe_pattern_warning(self):
        source='result=1\n'
        output=self._apply(source,missing_syntax=['데코레이터 사용'])
        self.assertEqual(output[0],source)

    def test_other_tags_remain(self):
        actions=[x['action'] for x in build_transform_plan(diff(missing_syntax=['데코레이터 사용','리스트 컴프리헨션']))['actions']]
        self.assertIn('create_safe_method_decorator',actions)
        self.assertIn('create_safe_comprehension_collection',actions)


if __name__ == '__main__':
    unittest.main()
