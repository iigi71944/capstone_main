"""Conservative syntax-family integration and negative-case regression tests."""
import ast
import contextlib
import io
import unittest
from unittest.mock import patch

from app.services.improvement.safe_set_comprehension_service import (
    transform_for_add_to_set_comprehension as set_comp,
    transform_set_comprehension_to_for_add as set_loop,
)
from app.services.improvement.safe_syntax_patterns_service import (
    transform_lambda_to_def as lambda_def,
    transform_def_to_lambda as def_lambda,
    transform_if_to_match as if_match,
    transform_match_to_if as match_if,
    transform_add_local_type_hints as type_add,
    transform_remove_local_type_hints as type_remove,
)
from app.services.style_tag_transform_map_service import (
    PLANNED_TAG_FAMILY, get_create_action_for_tag, get_tag_transform_status,
)
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_apply_service import _get_transform_function, apply_coding_style


def _observe(src):
    namespace = {}
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            exec(compile(src, '<test>', 'exec'), namespace)
            error = None
        except Exception as exc:
            error = (type(exc).__name__, str(exc))
    return out.getvalue(), error, namespace.get('result'), namespace.get('output')


def equal(source, fn, expect_change=True):
    transformed = fn(source)
    ast.parse(transformed)
    assert _observe(source) == _observe(transformed), (source, transformed, _observe(source), _observe(transformed))
    if expect_change:
        assert transformed != source, (fn.__name__, source)
    return transformed


def diff(*, missing_syntax=(), missing_concept=(), style_syntax=(), style_concept=(), target_syntax=()):
    return {'missing_syntax_tags':[{'tag':x} for x in missing_syntax],
            'missing_concept_tags':[{'tag':x} for x in missing_concept],
            'style_syntax_names':set(style_syntax),
            'style_concept_names':set(style_concept),
            'target_syntax_names':set(target_syntax),
            'target_concept_names':set(),
            'style_metrics':{}, 'target_analysis':{'metrics':{}}}


def plan(d):
    return [item['action'] for item in build_transform_plan(d)['actions']]


class SetFamilyTests(unittest.TestCase):
    def test_simple_collapse(self):
        s='result = set()\nfor x in [1,2,3]:\n    result.add(x*x)\nprint(result)\n'
        self.assertIn('result = {', equal(s,set_comp))

    def test_filter_collapse(self):
        s='result = set()\nfor x in [1,2,3,4]:\n    if x > 2:\n        result.add(x)\n'
        equal(s,set_comp)

    def test_two_filters(self):
        s='result = set()\nfor x in [1,2,3,4]:\n    if x > 1:\n        if x < 4:\n            result.add(x)\n'
        equal(s,set_comp)

    def test_unpack(self):
        s='result = set()\nfor x, y in [(1,2),(3,4)]:\n    result.add(x+y)\n'
        equal(s,set_comp)

    def test_literal_range(self):
        s='result = set()\nfor x in range(4):\n    result.add(x*x)\n'
        equal(s,set_comp)

    def test_expand_simple(self):
        s='result = {x*x for x in [1,2,3]}\nprint(result)\n'
        self.assertIn('.add(',equal(s,set_loop))

    def test_expand_filter(self):
        s='result = {x for x in [1,2,3] if x>1}\nprint(result)\n'
        equal(s,set_loop)

    def test_expand_unpack(self):
        s='result = {x+y for x, y in [(1,2),(3,4)]}\n'
        equal(s,set_loop)

    def test_expand_preserves_existing_result_on_error(self):
        s="result = {88}\ntry:\n    result = {1//x for x in [1,0]}\nexcept ZeroDivisionError:\n    pass\nprint(result)\n"
        equal(s,set_loop)

    def test_no_outside_names_leak(self):
        s='result = {x for x in [1,2]}\noutput = sorted(result)\n'
        transformed=equal(s,set_loop)
        self.assertNotIn('x = ',transformed)

    def test_skip_loop_target_used_after(self):
        s='result=set()\nfor x in [1,2]:\n    result.add(x)\nprint(x)\n'
        self.assertEqual(set_comp(s),s)

    def test_skip_result_depends_on_itself(self):
        s='result=set()\nfor x in result:\n    result.add(x)\n'
        self.assertEqual(set_comp(s),s)

    def test_skip_shadowed_set(self):
        s='set = lambda: []\nresult=set()\nfor x in [1,2]:\n    result.add(x)\n'
        self.assertEqual(set_comp(s),s)

    def test_skip_collapse_user_function(self):
        s='result=set()\nfor x in items():\n    result.add(x)\n'
        self.assertEqual(set_comp(s),s)

    def test_skip_comment_in_loop(self):
        s='result = set()\nfor x in [1]:\n    # keep\n    result.add(x)\n'
        self.assertEqual(set_comp(s),s)

    def test_skip_comp_user_call(self):
        s='result={f(x) for x in [1,2]}\n'
        self.assertEqual(set_loop(s),s)

    def test_skip_comp_multigenerator(self):
        s='result={x+y for x in [1] for y in [2]}\n'
        self.assertEqual(set_loop(s),s)

    def test_skip_introspection(self):
        s='result={x for x in [1,2]}\nprint(locals())\n'
        self.assertEqual(set_loop(s),s)

    def test_comment_outside_kept(self):
        s='# head\nresult=set()\nfor x in [1]:\n    result.add(x)\n# tail\n'
        t=equal(s,set_comp)
        self.assertIn('# head',t)
        self.assertIn('# tail',t)

    def test_idempotent(self):
        s='result=set()\nfor x in [1,2]:\n    result.add(x)\n'
        transformed=set_comp(s)
        self.assertEqual(set_comp(transformed),transformed)


class LambdaFamilyTests(unittest.TestCase):
    def test_forward(self):
        s='def f(x):\n    return x*x\nresult=f(3)\n'
        self.assertIn('lambda x:',equal(s,def_lambda))

    def test_reverse(self):
        s='f = lambda x: x*x\nresult=f(3)\n'
        self.assertIn('def f(',equal(s,lambda_def))

    def test_nested_scope(self):
        s='def outer():\n    f = lambda x: x+3\n    return f(4)\nresult=outer()\n'
        equal(s,lambda_def)

    def test_skip_decorator(self):
        s='@wrapper\ndef f(x):\n    return x\n'
        self.assertEqual(def_lambda(s),s)

    def test_skip_annotation(self):
        s='def f(x: int):\n    return x+1\n'
        self.assertEqual(def_lambda(s),s)

    def test_skip_multiple_statements(self):
        s='def f(x):\n    print(x)\n    return x\n'
        self.assertEqual(def_lambda(s),s)

    def test_skip_introspection(self):
        s='f=lambda x:x\nprint(f.__name__)\n'
        self.assertEqual(lambda_def(s),s)

    def test_skip_comment(self):
        s='def f(x):\n    # important\n    return x\n'
        self.assertEqual(def_lambda(s),s)

    def test_skip_class_body(self):
        s='class C:\n    f=lambda x:x\n'
        self.assertEqual(lambda_def(s),s)

    def test_skip_generator(self):
        s='f=lambda x: (yield x)\n'
        self.assertEqual(lambda_def(s),s)

    def test_skip_recursion(self):
        s='def f(x):\n    return f(x-1)\n'
        self.assertEqual(def_lambda(s),s)

    def test_skip_function_object_reference(self):
        s='f = lambda x:x+1\noutput = f\n'
        self.assertEqual(lambda_def(s),s)

    def test_skip_function_object_argument(self):
        s='def f(x):\n    return x+1\nuse(f)\n'
        self.assertEqual(def_lambda(s),s)


class PatternFamilyTests(unittest.TestCase):
    def test_to_match(self):
        s='v=2\nif v==1:\n    result="a"\nelif v==2:\n    result="b"\nelse:\n    result="c"\n'
        self.assertIn('match v:',equal(s,if_match))

    def test_to_if(self):
        s='v=2\nmatch v:\n    case 1:\n        result="a"\n    case 2:\n        result="b"\n    case _:\n        result="c"\n'
        self.assertIn('if v == 1:',equal(s,match_if))

    def test_no_default(self):
        s='v=5\nmatch v:\n    case 1:\n        result=1\n    case 2:\n        result=2\n'
        equal(s,match_if)

    def test_skip_unknown_object(self):
        s='if v==1:\n    result=1\nelse:\n    result=2\n'
        self.assertEqual(if_match(s),s)

    def test_skip_guard(self):
        s='v=2\nmatch v:\n    case 2 if True:\n        result=2\n'
        self.assertEqual(match_if(s),s)

    def test_skip_capture(self):
        s='v=2\nmatch v:\n    case x:\n        result=x\n'
        self.assertEqual(match_if(s),s)

    def test_skip_bool_pattern(self):
        s='v=True\nif v==True:\n    result=1\nelse:\n    result=2\n'
        self.assertEqual(if_match(s),s)

    def test_skip_header_comment(self):
        s='v=2\nif v==1: # keep\n    result=1\nelse:\n    result=2\n'
        self.assertEqual(if_match(s),s)

    def test_class_method(self):
        s='class A:\n    def f(self):\n        v=2\n        if v==1:\n            return 1\n        else:\n            return 2\nresult=A().f()\n'
        equal(s,if_match)


class AnnotationFamilyTests(unittest.TestCase):
    def test_int_local(self):
        s='def f():\n    x=10\n    return x\nresult=f()\n'
        self.assertIn('x: int = 10',equal(s,type_add))

    def test_str_local(self):
        s='def f():\n    x="hi"\n    return x\nresult=f()\n'
        self.assertIn('x: str =',equal(s,type_add))

    def test_bool_local(self):
        s='def f():\n    x=True\n    return x\nresult=f()\n'
        self.assertIn('x: bool = True',equal(s,type_add))

    def test_float_local(self):
        s='def f():\n    x=1.5\n    return x\nresult=f()\n'
        self.assertIn('x: float =',equal(s,type_add))

    def test_reverse(self):
        s='def f():\n    x: int=10\n    return x\nresult=f()\n'
        self.assertIn('x = 10',equal(s,type_remove))

    def test_skip_module(self):
        s='x=10\n'
        self.assertEqual(type_add(s),s)

    def test_skip_class(self):
        s='class C:\n    x=10\n'
        self.assertEqual(type_add(s),s)

    def test_skip_bad_annotation(self):
        s='def f():\n    x: custom = 10\n    return x\n'
        self.assertEqual(type_remove(s),s)

    def test_skip_none(self):
        s='def f():\n    x = None\n    return x\n'
        self.assertEqual(type_add(s),s)

    def test_skip_comment(self):
        s='def f():\n    x=10 # keep\n    return x\n'
        self.assertEqual(type_add(s),s)


class StyleIntegrationTests(unittest.TestCase):
    def test_registry_family_status(self):
        for name in ['세트 컴프리헨션','lambda식','타입 힌트 사용','타입 명시 코드 구조','패턴 매칭','패턴 매칭 구조']:
            with self.subTest(tag=name):
                self.assertEqual(get_tag_transform_status(name),'linked')
                self.assertNotIn(name,PLANNED_TAG_FAMILY)
                self.assertIsNotNone(_get_transform_function(get_create_action_for_tag(name)))

    def test_old_public_names_unchanged(self):
        self.assertEqual(get_create_action_for_tag('리스트 누적 방식 사용'),'create_append_collection')
        self.assertEqual(get_create_action_for_tag('딕셔너리 컴프리헨션'),'create_dict_comprehension')

    def test_forward_set(self):
        self.assertEqual(plan(diff(missing_syntax=['세트 컴프리헨션'])),['create_safe_set_comprehension'])

    def test_reverse_set(self):
        self.assertEqual(plan(diff(style_syntax=['for문'],style_concept=['상태 변경 중심 구조'],target_syntax=['세트 컴프리헨션'])),['create_safe_set_loop'])

    def test_forward_lambda(self):
        self.assertEqual(plan(diff(missing_syntax=['lambda식'])),['create_safe_lambda_expression'])

    def test_reverse_lambda(self):
        self.assertEqual(plan(diff(style_syntax=['함수 정의'],target_syntax=['lambda식'])),['create_safe_lambda_function'])

    def test_forward_match_dedup(self):
        self.assertEqual(plan(diff(missing_syntax=['패턴 매칭'],missing_concept=['패턴 매칭 구조'])),['create_safe_pattern_matching'])

    def test_reverse_match(self):
        self.assertEqual(plan(diff(style_syntax=['if문'],target_syntax=['패턴 매칭'])),['create_safe_pattern_if'])

    def test_forward_annotation_dedup(self):
        self.assertEqual(plan(diff(missing_syntax=['타입 힌트 사용'],missing_concept=['타입 명시 코드 구조'])),['create_safe_local_annotation'])

    def test_reverse_with_unrelated_action(self):
        value=plan(diff(missing_syntax=['리스트 컴프리헨션'],style_syntax=['함수 정의'],target_syntax=['lambda식']))
        self.assertIn('create_safe_comprehension_collection',value)
        self.assertIn('create_safe_lambda_function',value)

    def test_end_to_end(self):
        s='result=set()\nfor x in [1,2]:\n    result.add(x*x)\nprint(result)\n'
        sample=diff(missing_syntax=['세트 컴프리헨션'])
        with patch('app.services.style_apply_service.compare_style_with_target_code',return_value=sample),\
             patch('app.services.style_apply_service.compare_after_transform',return_value={'missing_syntax_tags':[],'missing_concept_tags':[]}),\
             patch('app.services.style_apply_service.verify_execution_equivalence',return_value={'status':'equivalent','equivalent':True,'message':'','function_verification':None}):
            result=apply_coding_style(s,{'syntax_tags':[],'concept_tags':[]})
        self.assertIn('result = {',result[0])
        self.assertEqual(_observe(result[0]),_observe(s))
        self.assertEqual(len(result),6)

    def test_reverse_without_evidence_not_selected(self):
        self.assertEqual(plan(diff(target_syntax=['세트 컴프리헨션'])),[])


if __name__ == '__main__':
    unittest.main()
