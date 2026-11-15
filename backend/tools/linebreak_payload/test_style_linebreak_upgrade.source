"""Linebreak-style extraction/application regression: no user code execution."""
from __future__ import annotations
import ast
import unittest
from app.services.style_format_profile_service import extract_formatting_style
from app.services.style_format_apply_service import apply_saved_formatting_style
from app.services.style_linebreak_service import (
    extract_linebreak_preferences,
    apply_context_blank_lines,
    apply_bracket_linebreaks,
)


def sig(code: str) -> str:
    return ast.dump(ast.parse(code), include_attributes=False)


def transfer(sample: str, target: str):
    p = extract_formatting_style(sample)
    converted, rules, warnings = apply_saved_formatting_style(target, p)
    assert sig(target) == sig(converted), warnings
    return converted, rules, warnings


class ExtractionTests(unittest.TestCase):
    def test_gap_between_module_functions(self):
        p=extract_linebreak_preferences('def a():\n    return 1\n\n\ndef b():\n    return 2\n')
        self.assertEqual(p['blank_lines_by_context']['between_top_level_functions']['preferred'],2)

    def test_class_methods(self):
        src='class C:\n    def x(self):\n        return 1\n\n    def y(self):\n        return 2\n'
        p=extract_linebreak_preferences(src)
        self.assertEqual(p['blank_lines_by_context']['between_class_methods']['preferred'],1)

    def test_before_control_flow(self):
        src='def f(xs):\n    total=0\n\n    for x in xs:\n        total+=x\n    return total\n'
        p=extract_linebreak_preferences(src)
        self.assertEqual(p['blank_lines_by_context']['before_control_flow']['preferred'],1)

    def test_before_return(self):
        src='def f(xs):\n    total=0\n\n    return total\n'
        self.assertEqual(extract_linebreak_preferences(src)['blank_lines_by_context']['before_return']['preferred'],1)

    def test_after_import(self):
        src='import math\n\nx=2\nprint(x)\n'
        self.assertEqual(extract_linebreak_preferences(src)['blank_lines_by_context']['after_imports']['preferred'],1)

    def test_gap_no_comment_inference(self):
        src='def f():\n    x=1\n    # explain return\n\n    return x\n'
        self.assertNotIn('before_return',extract_linebreak_preferences(src)['blank_lines_by_context'])

    def test_standalone_docstring_not_changed(self):
        src='def f():\n    """Line1\n\n    Line3"""\n    return 1\n'
        self.assertEqual(extract_formatting_style(src)['version'],1)

    def test_list_group_multiline_trailing(self):
        src='xs = [\n    1,\n    2,\n]\n'
        p=extract_linebreak_preferences(src)
        self.assertEqual(p['bracket_groups_by_kind']['[']['multiline_trailing_comma'],1)

    def test_list_group_without_trailing_comma(self):
        src='xs = [\n    1,\n    2\n]\n'
        p=extract_linebreak_preferences(src)
        self.assertEqual(p['bracket_groups_by_kind']['[']['multiline_trailing_comma'],0)

    def test_profile_v1_extra_fields(self):
        p=extract_formatting_style('def f():\n    a=1\n\n    return a\n')
        self.assertIn('blank_lines_by_context',p['line_layout'])
        self.assertIn('bracket_groups_by_kind',p['line_layout'])
        self.assertIn('observed_max_code_columns',p['line_layout'])


class ApplicationTests(unittest.TestCase):
    def test_add_blank_before_for_and_return(self):
        sample='def f(xs):\n    s=0\n\n    for x in xs:\n        s+=x\n\n    return s\n'
        target='def f(xs):\n    s=0\n    for x in xs:\n        s+=x\n    return s\n'
        new,r,_=transfer(sample,target)
        self.assertIn('s=0\n\n    for x',new)
        self.assertIn('s+=x\n\n    return s',new)
        self.assertTrue(any('빈 줄' in x for x in r))

    def test_remove_blanks(self):
        sample='def f(xs):\n    s=0\n    for x in xs:\n        s+=x\n    return s\n'
        target='def f(xs):\n    s=0\n\n    for x in xs:\n        s+=x\n\n    return s\n'
        new,_,_=transfer(sample,target)
        self.assertIn('s=0\n    for x',new)
        self.assertIn('s+=x\n    return s',new)

    def test_two_top_level_blanks(self):
        sample='def a():\n    return 1\n\n\ndef b():\n    return 2\n'
        target='def a():\n    return 1\ndef b():\n    return 2\n'
        new,_,_=transfer(sample,target)
        self.assertIn('return 1\n\n\ndef b()',new)

    def test_two_top_level_blanks_deleted(self):
        sample='def a():\n    return 1\n\ndef b():\n    return 2\n'
        target='def a():\n    return 1\n\n\ndef b():\n    return 2\n'
        new,_,_=transfer(sample,target)
        self.assertIn('return 1\n\ndef b()',new)

    def test_class_methods_gap(self):
        sample='class A:\n    def a(self):\n        return 1\n\n    def b(self):\n        return 2\n'
        target='class A:\n    def a(self):\n        return 1\n    def b(self):\n        return 2\n'
        new,_,_=transfer(sample,target)
        self.assertIn('return 1\n\n    def b',new)

    def test_comments_between_blocks_not_moved(self):
        sample='def f():\n    x=1\n\n    return x\n'
        target='def f():\n    x=1\n    # explanation\n    return x\n'
        new,_,_=transfer(sample,target)
        self.assertEqual(new,target)

    def test_decorator_kept_connected(self):
        sample='def a():\n    return 1\n\n\ndef b():\n    return 2\n'
        target='def a():\n    return 1\n@decorator\ndef b():\n    return 2\n'
        new,_,_=transfer(sample,target)
        self.assertIn('\n\n\n@decorator\ndef b():',new)

    def test_crlf_preserved(self):
        sample='def f():\r\n    x=1\r\n\r\n    return x\r\n'
        target='def f():\r\n    x=1\r\n    return x\r\n'
        new,_,_=transfer(sample,target)
        self.assertIn('x=1\r\n\r\n    return',new)
        self.assertNotIn('\n\n',new)

    def test_unicode_and_comments(self):
        sample='def f():\n    과일=1\n\n    return 과일\n'
        target='def f():\n    과일=1\n    return 과일\n'
        new,_,_=transfer(sample,target)
        self.assertIn('과일=1\n\n    return 과일',new)

    def test_idempotent(self):
        sample='def f(xs):\n    s=0\n\n    for x in xs:\n        s+=x\n\n    return s\n'
        target='def f(xs):\n  s=0\n  for x in xs:\n    s+=x\n  return s\n'
        once,_,_=transfer(sample,target)
        twice,_,_=transfer(sample,once)
        self.assertEqual(once,twice)

    def test_long_code_350_lines(self):
        sample='def f():\n    x=1\n\n    return x\n'
        funcs=['def f%d():\n    x=%d\n    return x\n'%(i,i) for i in range(120)]
        target='\n'.join(funcs)
        self.assertGreater(len(target.splitlines()),350)
        new,_,_=transfer(sample,target)
        self.assertEqual(sig(new),sig(target))
        self.assertIn('x=0\n\n    return x',new)

    def test_old_saved_v1_without_extra_newline_keys(self):
        sample='def f():\n    a=1\n    return a\n'
        target='def f():\n    a=1\n    return a\n'
        p=extract_formatting_style(sample)
        for key in ['blank_lines_by_context','bracket_groups_by_kind','observed_max_code_columns']:
            del p['line_layout'][key]
        out,_,_=apply_saved_formatting_style(target,p)
        self.assertEqual(out,target)

    def test_no_added_blanks_from_unobserved_category(self):
        sample='x=1\nprint(x)\n'
        target='def f():\n    x=1\n    return x\n'
        out,_,_=transfer(sample,target)
        self.assertEqual(out,target)

    def test_comment_inside_multiline_preserved(self):
        sample='x=[1,2,3]\n'
        target='x=[\n    1, # keep\n    2,\n    3,\n]\n'
        out,_,_=transfer(sample,target)
        self.assertEqual(out,target)

    def test_docstring_exact(self):
        sample='def f():\n    x=1\n\n    return x\n'
        target='def f():\n    s="""hello\n\nworld"""\n    return s\n'
        out,_,_=transfer(sample,target)
        self.assertIn('"""hello\n\nworld"""',out)


class BracketTests(unittest.TestCase):
    def test_expand_list_trailing(self):
        sample='xs=[\n    1,\n    2,\n    3,\n]\n'
        target='xs=[1,2,3]\n'
        out,r,_=transfer(sample,target)
        self.assertIn('xs=[\n    1,\n    2,\n    3,\n]',out)
        self.assertTrue(any('여러 줄' in x for x in r))

    def test_expand_list_without_trailing(self):
        sample='xs=[\n    1,\n    2\n]\n'
        out,_,_=transfer(sample,'xs=[1,2]\n')
        self.assertIn('    2\n]',out)

    def test_expand_dict(self):
        sample='values={\n    "a": 1,\n    "b": 2,\n}\n'
        out,_,_=transfer(sample,'values={"a": 1, "b": 2}\n')
        self.assertIn('    "a": 1,\n    "b": 2,\n}',out)

    def test_expand_call(self):
        sample='value=func(\n    1,\n    2,\n)\n'
        out,_,_=transfer(sample,'value=func(1,2)\n')
        self.assertIn('func(\n    1,\n    2,\n)',out)

    def test_compact_list(self):
        sample='xs=[1,2,3]\n'
        out,_,_=transfer(sample,'xs=[\n    1,\n    2,\n    3,\n]\n')
        self.assertIn('xs=[1, 2, 3]',out)

    def test_compact_dict(self):
        sample='d={"a":1,"b":2}\n'
        out,_,_=transfer(sample,'d={\n    "a":1,\n    "b":2,\n}\n')
        self.assertIn('d={"a":1, "b":2}',out)

    def test_compact_call(self):
        sample='v=fn(1,2)\n'
        out,_,_=transfer(sample,'v=fn(\n    1,\n    2,\n)\n')
        self.assertIn('v=fn(1, 2)',out)

    def test_keep_nested_bracket(self):
        sample='x=[[1,2], [3,4]]\n'
        target='x=[\n    [1,2],\n    [3,4],\n]\n'
        out,_,_=transfer(sample,target)
        self.assertEqual(out,target)

    def test_keep_comments_inside_brackets(self):
        sample='xs=[1,2]\n'
        target='xs=[\n    1,  # doc\n    2,\n]\n'
        out,_,_=transfer(sample,target)
        self.assertEqual(out,target)

    def test_keep_strings_with_commas(self):
        sample='xs=[\n    "a,b",\n    "c,d",\n]\n'
        out,_,_=transfer(sample,'xs=["a,b", "c,d"]\n')
        self.assertIn('    "a,b",\n    "c,d",',out)

    def test_keep_indexing(self):
        sample='xs=[\n    1,\n    2,\n]\n'
        target='x=grid[1,2]\n'
        out,_,_=transfer(sample,target)
        self.assertEqual(out,target)

    def test_keep_definition_parameters(self):
        sample='value=fn(\n    1,\n    2,\n)\n'
        target='def f(a,b):\n    return a+b\n'
        out,_,_=transfer(sample,target)
        self.assertEqual(out,target)

    def test_short_one_item_unchanged(self):
        sample='xs=[\n    1,\n    2,\n]\n'
        target='xs=[1]\n'
        out,_,_=transfer(sample,target)
        self.assertEqual(out,target)

    def test_long_single_line_not_compacted(self):
        sample='xs=[1,2]\n'
        target='xs=[\n    "' + ('a'*75) + '",\n    "' + ('b'*75) + '",\n]\n'
        out,_,_=transfer(sample,target)
        self.assertEqual(out,target)

    def test_mixed_bracket_style_long_line_wraps(self):
        sample='a=[1,2]\nb=[3,4]\nc=[\n    5,\n    6,\n]\n'
        target='x=[' + ', '.join(str(i) for i in range(40)) + ']\n'
        out,_,_=transfer(sample,target)
        self.assertIn('x=[\n',out)
        self.assertIn('    39',out)

    def test_mixed_bracket_style_short_line_stays_inline(self):
        sample='a=[1,2]\nb=[3,4]\nc=[\n    5,\n    6,\n]\n'
        target='x=[1,2]\n'
        out,_,_=transfer(sample,target)
        self.assertEqual(out,target)

    def test_bracket_profile_empty(self):
        target='xs=[1,2]\n'
        self.assertEqual(apply_bracket_linebreaks(target,{},'    '),target)

    def test_blank_profile_empty(self):
        target='def f():\n    return 1\n'
        self.assertEqual(apply_context_blank_lines(target,{}),target)

    def test_multiple_list_groups(self):
        sample='xs=[\n    1,\n    2,\n]\n'
        target='a=[1,2]\nb=[3,4]\n'
        out,_,_=transfer(sample,target)
        self.assertEqual(out.count('=[\n'),2)

    def test_new_lines_preserve_stdout(self):
        sample='xs=[\n    1,\n    2,\n]\n'
        target='xs=[1,2]\nprint(sum(xs))\n'
        out,_,_=transfer(sample,target)
        namespace_a={}; namespace_b={}
        import contextlib, io
        oa,ob=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(oa): exec(target,namespace_a)
        with contextlib.redirect_stdout(ob): exec(out,namespace_b)
        self.assertEqual(oa.getvalue(),ob.getvalue())


if __name__ == '__main__':
    unittest.main()
