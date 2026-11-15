"""Batch 4 narrow architecture pattern tests, including no-op safety cases."""
import ast
import contextlib
import io
import unittest
from unittest.mock import patch

from app.services.improvement.safe_architecture_patterns_service import (
    transform_extract_validation_helper as extract,
    transform_inline_validation_helper as inline,
    transform_from_math_to_module as math_import,
    transform_math_module_to_from as from_import,
    transform_type_to_class as to_class,
    transform_type_to_class_with_methods as to_methods,
)
from app.services.style_tag_transform_map_service import (
    get_create_action_for_tag, get_tag_transform_status, PLANNED_TAG_FAMILY,
)
from app.services.style_apply_service import _get_transform_function
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_transform_audit_service import audit_style_registry


def observe(src):
    out=io.StringIO()
    scope={}
    with contextlib.redirect_stdout(out):
        try:
            exec(compile(src,'<batch4>','exec'),scope)
            error=None
        except Exception as exc:
            error=(type(exc).__name__,str(exc))
    return out.getvalue(),error,{name:scope[name] for name in ('result','output','number') if name in scope}


def equivalent(test, source, func, keyword=None):
    changed=func(source)
    test.assertNotEqual(changed, source)
    ast.parse(changed)
    test.assertEqual(observe(source), observe(changed))
    if keyword:
        test.assertIn(keyword,changed)
    return changed


def plan(tags_syntax=(),tags_concept=()):
    d={'missing_syntax_tags':[{'tag':v} for v in tags_syntax],
       'missing_concept_tags':[{'tag':v} for v in tags_concept],
       'style_syntax_names':set(tags_syntax), 'style_concept_names':set(tags_concept),
       'target_syntax_names':set(), 'target_concept_names':set(),
       'style_metrics':{},'target_analysis':{'metrics':{}}}
    return [r['action'] for r in build_transform_plan(d)['actions']]


class FunctionSplitTests(unittest.TestCase):
    GUARD='def f(x):\n    if x < 0:\n        raise ValueError("negative")\n    return x * 2\nresult = f(3)\n'

    def test_positive(self): equivalent(self,self.GUARD,extract,'def __capstone_validate_x')
    def test_negative_exception(self): equivalent(self,self.GUARD.replace('f(3)','f(-1)'),extract,'raise ValueError')
    def test_zero(self): equivalent(self,self.GUARD.replace('f(3)','f(0)'),extract)
    def test_type_error(self): equivalent(self,self.GUARD.replace('ValueError','TypeError'),extract)
    def test_ge_check(self): equivalent(self,self.GUARD.replace('x < 0','x >= 2'),extract)
    def test_quoted_unicode(self): equivalent(self,self.GUARD.replace('negative','음수'),extract)
    def test_unicode_parameter(self): equivalent(self,self.GUARD.replace('x','숫자'),extract)
    def test_multifunction(self):
        s=self.GUARD+'\ndef g(y):\n    if y == 0:\n        raise TypeError("zero")\n    return y + 2\noutput = g(2)\n'
        changed=equivalent(self,s,extract)
        self.assertEqual(changed.count('def __capstone_validate_'),2)
    def test_helper_collision(self):
        s='__capstone_validate_x = 1\n'+self.GUARD
        equivalent(self,s,extract,'__capstone_validate_x_1')
    def test_preserve_outside_comments(self):
        s='# before\n'+self.GUARD+'# after\n'
        out=equivalent(self,s,extract)
        self.assertIn('# before',out)
        self.assertIn('# after',out)
    def test_reverse(self): equivalent(self,extract(self.GUARD),inline,'if x < 0')
    def test_roundtrip(self): self.assertEqual(observe(self.GUARD),observe(inline(extract(self.GUARD))))
    def test_idempotence(self):
        x=extract(self.GUARD)
        self.assertEqual(x,extract(x))
    def test_skip_in_function_comment(self):
        s=self.GUARD.replace('    return x * 2','    # important\n    return x * 2')
        self.assertEqual(extract(s),s)
    def test_skip_docstring(self):
        s=self.GUARD.replace('    if x < 0','    """docs"""\n    if x < 0')
        self.assertEqual(extract(s),s)
    def test_skip_two_params(self):
        s=self.GUARD.replace('f(x)','f(x, y)')
        self.assertEqual(extract(s),s)
    def test_skip_decorator(self):
        s='@staticmethod\n'+self.GUARD
        self.assertEqual(extract(s),s)
    def test_skip_complex_guard(self):
        s=self.GUARD.replace('if x < 0','if check(x)')
        self.assertEqual(extract(s),s)
    def test_skip_conditional_return(self):
        s=self.GUARD.replace('return x * 2','return sum([x])')
        self.assertEqual(extract(s),s)
    def test_skip_introspection(self):
        s=self.GUARD+'print(globals())\n'
        self.assertEqual(extract(s),s)
    def test_skip_shadowed_value_error(self):
        s='ValueError = TypeError\n'+self.GUARD
        self.assertEqual(extract(s),s)
    def test_skip_semicolon(self):
        s=self.GUARD.replace('    return x * 2','    return x * 2; print("x")')
        self.assertEqual(extract(s),s)
    def test_invalid(self): self.assertEqual(extract('def f(:\n'), 'def f(:\n')


class MathImportTests(unittest.TestCase):
    SRC='def f(x):\n    from math import sqrt\n    return sqrt(x)\nresult = f(9)\n'
    def test_sqrt_forward(self): equivalent(self,self.SRC,math_import,'import math')
    def test_reverse(self): equivalent(self,math_import(self.SRC),from_import,'from math import sqrt')
    def test_roundtrip(self): self.assertEqual(observe(self.SRC),observe(from_import(math_import(self.SRC))))
    def test_negative_domain_exception(self): equivalent(self,self.SRC.replace('f(9)','f(-9)'),math_import)
    def test_zero(self): equivalent(self,self.SRC.replace('f(9)','f(0)'),math_import)
    def test_floor(self): equivalent(self,self.SRC.replace('sqrt','floor'),math_import)
    def test_ceil(self): equivalent(self,self.SRC.replace('sqrt','ceil'),math_import)
    def test_fabs(self): equivalent(self,self.SRC.replace('sqrt','fabs'),math_import)
    def test_sin(self): equivalent(self,self.SRC.replace('sqrt','sin'),math_import)
    def test_cos(self): equivalent(self,self.SRC.replace('sqrt','cos'),math_import)
    def test_tan(self): equivalent(self,self.SRC.replace('sqrt','tan'),math_import)
    def test_unicode_function(self): equivalent(self,self.SRC.replace('def f(x):','def 계산(x):').replace('f(9)','계산(9)'),math_import)
    def test_comments_preserved(self):
        s='# top\n'+self.SRC+'# bottom\n'
        out=equivalent(self,s,math_import)
        self.assertTrue(out.startswith('# top'))
        self.assertIn('# bottom',out)
    def test_idempotent(self):
        out=math_import(self.SRC)
        self.assertEqual(out,math_import(out))
    def test_skip_math_alias(self):
        s=self.SRC.replace('from math import sqrt','from math import sqrt as s').replace('return sqrt(x)','return s(x)')
        self.assertEqual(math_import(s),s)
    def test_skip_shadowed_function(self):
        s=self.SRC+'sqrt = lambda x: 3\n'
        self.assertEqual(math_import(s),s)
    def test_skip_other_import(self):
        s='import os\n'+self.SRC
        self.assertEqual(math_import(s),s)
    def test_skip_comment_inside(self):
        s=self.SRC.replace('    return sqrt(x)','    # keep\n    return sqrt(x)')
        self.assertEqual(math_import(s),s)
    def test_skip_call_dynamic(self):
        s=self.SRC.replace('sqrt(x)','sqrt(x + 1)')
        self.assertEqual(math_import(s),s)
    def test_skip_introspection(self):
        s='print(locals())\n'+self.SRC
        self.assertEqual(math_import(s),s)
    def test_skip_parameter_same_as_module(self):
        s=self.SRC.replace('def f(x):','def f(math):').replace('sqrt(x)','sqrt(math)')
        self.assertEqual(math_import(s),s)
    def test_skip_argument_same_as_member(self):
        s=self.SRC.replace('sqrt(x)','sqrt(sqrt)')
        self.assertEqual(math_import(s),s)
    def test_skip_reverse_argument_name_clash(self):
        s='def f(x):\n    import math\n    return math.sqrt(sqrt)\n'
        self.assertEqual(from_import(s),s)
    def test_skip_keyword_call(self):
        s=self.SRC.replace('sqrt(x)','sqrt(x=x)')
        self.assertEqual(math_import(s),s)
    def test_skip_class_member(self):
        s='class C:\n    '+self.SRC.replace('\n','\n    ').rstrip()+'\n'
        self.assertEqual(math_import(s),s)
    def test_invalid(self): self.assertEqual(math_import('def x(:\n'),'def x(:\n')


class StaticClassTests(unittest.TestCase):
    SRC='Box = type("Box", (), {"side": 2})\nresult = Box.side\n'
    def test_basic(self): equivalent(self,self.SRC,to_class,'class Box:')
    def test_boolean(self): equivalent(self,self.SRC.replace('2','True'),to_class)
    def test_string_value(self): equivalent(self,self.SRC.replace('2','"hi"'),to_class)
    def test_float_value(self): equivalent(self,self.SRC.replace('2','3.5'),to_class)
    def test_none_value(self): equivalent(self,self.SRC.replace('2','None'),to_class)
    def test_multiple_fields(self):
        s='Box = type("Box", (), {"side": 2, "height": 4})\nresult = Box.side + Box.height\n'
        out=equivalent(self,s,to_class)
        self.assertIn('height = 4',out)
    def test_unicode_fields(self): equivalent(self,'상자=type("상자",(),{"크기":4})\nresult=상자.크기\n',to_class)
    def test_keep_comments(self):
        out=equivalent(self,'# top\n'+self.SRC+'# bottom\n',to_class)
        self.assertIn('# bottom',out)
    def test_idempotent(self):
        out=to_class(self.SRC)
        self.assertEqual(to_class(out),out)
    def test_skip_unsafe_bases(self):
        s=self.SRC.replace('(),','(object,),')
        self.assertEqual(to_class(s),s)
    def test_skip_dynamic_field(self):
        s=self.SRC.replace('"side": 2','"side": get_value()')
        self.assertEqual(to_class(s),s)
    def test_skip_missing_fields(self):
        s=self.SRC.replace('{"side": 2}','{}')
        self.assertEqual(to_class(s),s)
    def test_skip_name_mismatch(self):
        s=self.SRC.replace('type("Box"','type("NotBox"')
        self.assertEqual(to_class(s),s)
    def test_skip_type_shadowed(self):
        s='type = lambda *a: 5\n'+self.SRC
        self.assertEqual(to_class(s),s)
    def test_skip_class_rebinding(self):
        s=self.SRC+'Box=123\n'
        self.assertEqual(to_class(s),s)
    def test_skip_comment_on_factory(self):
        s=self.SRC.replace('})','}) # keep')
        self.assertEqual(to_class(s),s)
    def test_skip_class_attribute_inspection(self):
        s=self.SRC+'print(Box.__dict__)\n'
        self.assertEqual(to_class(s),s)
    def test_skip_semicolon(self):
        s='Box = type("Box", (), {"side": 2});print(Box)\n'
        self.assertEqual(to_class(s),s)
    def test_skip_class_body_method_on_simple_action(self):
        s='def add(x):\n    return x + 1\nA = type("A", (), {"add": staticmethod(add)})\n'
        self.assertEqual(to_class(s),s)
    def test_invalid(self): self.assertEqual(to_class('Box = type('),'Box = type(')


class StaticMethodClassTests(unittest.TestCase):
    SRC='def add(x):\n    return x+1\nTool = type("Tool", (), {"add": staticmethod(add)})\nresult = Tool.add(3)\n'
    def test_basic(self): equivalent(self,self.SRC,to_methods,'class Tool:')
    def test_with_literal_field(self):
        s='def add(x):\n    return x+1\nTool = type("Tool", (), {"add": staticmethod(add),"limit":5})\nresult = Tool.add(Tool.limit)\n'
        equivalent(self,s,to_methods,'limit = 5')
    def test_unicode(self):
        s='def 값(x):\n    return x+1\nTool = type("Tool", (), {"값": staticmethod(값)})\nresult = Tool.값(3)\n'
        equivalent(self,s,to_methods)
    def test_multiple_methods(self):
        s='def plus(x):\n    return x+1\ndef times(x):\n    return x*2\nTool=type("Tool",(),{"plus":staticmethod(plus),"times":staticmethod(times)})\nresult=Tool.plus(1)+Tool.times(2)\n'
        equivalent(self,s,to_methods)
    def test_idempotent(self):
        out=to_methods(self.SRC)
        self.assertEqual(to_methods(out),out)
    def test_keep_outside_comment(self):
        out=equivalent(self,'# comment\n'+self.SRC+'# end\n',to_methods)
        self.assertIn('# comment',out)
    def test_skip_no_function(self):
        s='Tool=type("Tool",(),{"add":staticmethod(add)})\n'
        self.assertEqual(to_methods(s),s)
    def test_skip_function_defined_after(self):
        s='Tool=type("Tool",(),{"add":staticmethod(add)})\ndef add(x):\n    return x+1\n'
        self.assertEqual(to_methods(s),s)
    def test_skip_dynamic_member(self):
        s=self.SRC.replace('staticmethod(add)','classmethod(add)')
        self.assertEqual(to_methods(s),s)
    def test_skip_nonstatic_call(self):
        s=self.SRC.replace('staticmethod(add)','make_method(add)')
        self.assertEqual(to_methods(s),s)
    def test_skip_rebinding_method_function(self):
        s=self.SRC+'add = lambda x: 0\n'
        self.assertEqual(to_methods(s),s)
    def test_skip_introspection(self):
        s=self.SRC+'print(Tool.__dict__)\n'
        self.assertEqual(to_methods(s),s)
    def test_skip_class_name_mismatch(self):
        s=self.SRC.replace('"Tool"','"Wrong"')
        self.assertEqual(to_methods(s),s)
    def test_skip_comment_inline(self):
        s=self.SRC.replace('})','}) # inline')
        self.assertEqual(to_methods(s),s)
    def test_skip_type_shadowing(self):
        s='type = 3\n'+self.SRC
        self.assertEqual(to_methods(s),s)
    def test_skip_anonymous_lambda(self):
        s=self.SRC.replace('staticmethod(add)','staticmethod(lambda x: x+1)')
        self.assertEqual(to_methods(s),s)
    def test_invalid(self): self.assertEqual(to_methods('def x(:\n'),'def x(:\n')


class RegistryWiringTests(unittest.TestCase):
    def test_all_four_tags_linked(self):
        for tag in ['단일 책임 함수 구조','모듈 의존 구조','클래스 정의','클래스 중심 코드 구조']:
            with self.subTest(tag=tag):
                self.assertEqual(get_tag_transform_status(tag),'linked')
                self.assertNotIn(tag,PLANNED_TAG_FAMILY)
                self.assertIsNotNone(_get_transform_function(get_create_action_for_tag(tag)))
    def test_no_stale_planned_items(self): self.assertEqual(len(PLANNED_TAG_FAMILY),0)
    def test_audit_valid(self): self.assertEqual(audit_style_registry()['issues'], [])
    def test_plan_single_responsibility(self): self.assertIn('create_safe_validation_helper',plan(tags_concept=['단일 책임 함수 구조']))
    def test_plan_math(self): self.assertIn('create_safe_math_module_import',plan(tags_concept=['모듈 의존 구조']))
    def test_plan_class(self): self.assertIn('create_safe_explicit_class',plan(tags_syntax=['클래스 정의']))
    def test_plan_class_methods(self): self.assertIn('create_safe_class_methods',plan(tags_concept=['클래스 중심 코드 구조']))
    def test_other_actions_stay(self):
        p=plan(tags_concept=['모듈 의존 구조','정렬 중심 구조'])
        self.assertIn('create_safe_math_module_import',p)
        self.assertIn('create_sort_style',p)
    def test_forward_functions_wired(self):
        pairs={'create_safe_validation_helper':extract,
               'create_safe_math_module_import':math_import,
               'create_safe_explicit_class':to_class,
               'create_safe_class_methods':to_methods}
        for key,func in pairs.items():
            self.assertIs(_get_transform_function(key),func)
    def _apply(self, source, syntax=(), concept=(), verdict='equivalent'):
        from app.services import style_apply_service as app
        d={'missing_syntax_tags':[{'tag':v} for v in syntax],
           'missing_concept_tags':[{'tag':v} for v in concept],
           'style_syntax_names':set(syntax),'style_concept_names':set(concept),
           'target_syntax_names':set(),'target_concept_names':set(),
           'style_metrics':{},'target_analysis':{'metrics':{}}}
        with patch.object(app,'compare_style_with_target_code',return_value=d), \
             patch.object(app,'compare_after_transform',return_value={'missing_syntax_tags':[],'missing_concept_tags':[]}), \
             patch.object(app,'verify_execution_equivalence',return_value={'status':verdict,'equivalent':verdict=='equivalent','message':'test','function_verification':None}):
            return app.apply_coding_style(source,{})
    def test_apply_validation(self):
        src=FunctionSplitTests.GUARD
        changed=self._apply(src,concept=['단일 책임 함수 구조'])[0]
        self.assertIn('def __capstone_validate_x',changed)
        self.assertEqual(observe(src),observe(changed))
    def test_apply_module(self):
        src=MathImportTests.SRC
        changed=self._apply(src,concept=['모듈 의존 구조'])[0]
        self.assertIn('import math',changed)
        self.assertEqual(observe(src),observe(changed))
    def test_apply_class(self):
        src=StaticClassTests.SRC
        changed=self._apply(src,syntax=['클래스 정의'])[0]
        self.assertIn('class Box',changed)
        self.assertEqual(observe(src),observe(changed))
    def test_apply_class_methods(self):
        src=StaticMethodClassTests.SRC
        changed=self._apply(src,concept=['클래스 중심 코드 구조'])[0]
        self.assertIn('class Tool',changed)
        self.assertEqual(observe(src),observe(changed))
    def test_apply_rollback_if_different(self):
        src=FunctionSplitTests.GUARD
        transformed=self._apply(src,concept=['단일 책임 함수 구조'],verdict='different')
        self.assertEqual(transformed[0],src)
    def test_apply_no_change_if_no_pattern(self):
        src='result=2\n'
        changed=self._apply(src,syntax=['클래스 정의'])
        self.assertEqual(changed[0],src)

    def test_reverse_helpers_wired(self):
        pairs={'create_safe_inline_validation':inline,
               'create_safe_math_member_import':from_import}
        for key,func in pairs.items():
            self.assertIs(_get_transform_function(key),func)


if __name__=='__main__':
    unittest.main()
