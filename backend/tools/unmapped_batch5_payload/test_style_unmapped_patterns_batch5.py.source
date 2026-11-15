"""Finite fixed-fixture tests for the fifth incremental tag batch.

Run from backend/: python -m unittest discover -s tests -v
These source strings are embedded trusted examples, never external user code.
"""
from __future__ import annotations

import ast
import contextlib
import io
import unittest

from app.services.improvement.safe_unmapped_patterns_batch5_service import (
    transform_to_known_key_indexing as transform,
)


def observe(source: str) -> tuple:
    out = io.StringIO()
    scope: dict = {}
    with contextlib.redirect_stdout(out):
        exec(compile(source, '<fixed-batch5-fixture>', 'exec'), scope)
    result = scope.get('result')
    return (out.getvalue(), type(result).__name__, repr(result))


class IndexingTagTests(unittest.TestCase):
    def changed(self, source: str, marker: str) -> str:
        new = transform(source)
        self.assertNotEqual(source, new)
        ast.parse(new)
        self.assertIn(marker, new)
        self.assertEqual(observe(source), observe(new))
        self.assertEqual(new, transform(new))
        return new

    def unchanged(self, source: str) -> None:
        self.assertEqual(source, transform(source))

    def test_basic_literal_key(self):
        self.changed("data={'a': 5}\nresult=data.get('a')\n", "data['a']")

    def test_additional_integer_key(self):
        self.changed('data={10: "ten"}\nresult=data.get(10)\n', 'data[10]')

    def test_complex_function_return(self):
        self.changed("def f():\n    data={'x': 2}\n    return data.get('x')\nresult=f()\n", "data['x']")

    def test_two_keys_in_same_statement(self):
        self.changed("data={'x':2,'y':3}\nresult=(data.get('x'),data.get('y'))\n", "data['y']")

    def test_list_with_known_keys(self):
        self.changed("data={'x':2,'y':3}\nresult=[data.get('x'),data.get('y')]\n", "data['x']")

    def test_negative_int_key(self):
        self.changed("data={-2:10}\nresult=data.get(-2)\n", 'data[-2]')

    def test_positive_int_key(self):
        self.changed("data={+2:10}\nresult=data.get(+2)\n", 'data[+2]')

    def test_assign_to_result(self):
        self.changed('d={1:"one"}\nresult=d.get(1)\n', 'd[1]')

    def test_unicode_value_and_key(self):
        self.changed("d={'한글':'값'}\nresult=d.get('한글')\n", "d['한글']")

    def test_bytes_splice_preserves_unrelated_unicode(self):
        src = "# 한국어 원본\nd={'한글':'값'}\nresult=d.get('한글')\n# 유지\n"
        edited = self.changed(src, 'd[')
        self.assertTrue(edited.startswith('# 한국어 원본\n'))
        self.assertTrue(edited.endswith('# 유지\n'))

    def test_crlf_kept(self):
        out = self.changed("d={'a':1}\r\nresult=d.get('a')\r\n", "d['a']")
        self.assertNotIn('\n', out.replace('\r\n', ''))

    def test_two_spaces_indentation(self):
        self.changed("def f():\n  d={'a':1}\n  return d.get('a')\nresult=f()\n", "d['a']")

    def test_function_with_unrelated_comment(self):
        src = "def f():\n    # dictionary\n    d={'a':1}\n    return d.get('a') # result\nresult=f()\n"
        out = self.changed(src, "d['a']")
        self.assertIn('# result', out)

    def test_builtin_non_shadow_dependency(self):
        self.changed("d={'x':10}\nresult=d.get('x') + 1\n", "d['x']")

    def test_zero_and_empty_value(self):
        self.changed("d={'x':0}\nresult=d.get('x')\n", "d['x']")

    def test_none_value(self):
        self.changed("d={'x':None}\nresult=d.get('x')\n", "d['x']")

    def test_read_in_conditional(self):
        self.changed("d={'x':1}\nif d.get('x'):\n    result='yes'\nelse:\n    result='no'\n", "d['x']")

    def test_two_separate_sites(self):
        self.changed("a={'x':1}\nfirst=a.get('x')\nb={'y':2}\nresult=b.get('y')\n", "b['y']")

    def test_skip_missing_key(self):
        self.unchanged("d={'x':1}\nresult=d.get('z')\n")

    def test_skip_default_argument(self):
        self.unchanged("d={'x':1}\nresult=d.get('x',0)\n")

    def test_skip_dynamic_key(self):
        self.unchanged("d={'x':1}\nk='x'\nresult=d.get(k)\n")

    def test_skip_adjacent_rebinding(self):
        # The second binding is immediate and safe; only the nearest literal
        # binding should be taken as evidence for a local rewrite.
        self.unchanged("d={'x':1}\nd=unknown\nresult=d.get('x')\n")

    def test_skip_intervening_mutation(self):
        self.unchanged("d={'x':1}\nd.clear()\nresult=d.get('x')\n")

    def test_skip_nonliteral_dict_value(self):
        self.unchanged("d={'x':load()}\nresult=d.get('x')\n")

    def test_skip_dict_unpack(self):
        self.unchanged("d={'x':1,**other}\nresult=d.get('x')\n")

    def test_skip_dict_comprehension(self):
        self.unchanged("d={k:v for k,v in pairs}\nresult=d.get('x')\n")

    def test_skip_sensitive_locals(self):
        self.unchanged("d={'x':1}\nresult=(locals(),d.get('x'))\n")

    def test_skip_nested_dynamic_other_call(self):
        self.unchanged("d={'x':1}\nresult=(d.get('x'),d.pop('x'))\n")

    def test_skip_unsafe_dict_target_reassignment(self):
        self.unchanged("d={'x':1}\nd=d.get('x')\n")

    def test_skip_multiline_call(self):
        self.unchanged("d={'x':1}\nresult=d.get(\n    'x'\n)\n")

    def test_skip_class_method_calls_not_literal(self):
        self.unchanged("class A:\n    def get(self,k): return 1\nd=A()\nresult=d.get('x')\n")

    def test_skip_invalid_source(self):
        self.unchanged('if:')

    def test_skip_no_target(self):
        self.unchanged("d={'x':1}\nresult=1\n")

    def test_skip_key_float(self):
        self.unchanged("d={1.2:'x'}\nresult=d.get(1.2)\n")

    def test_no_semantic_mismatch_on_duplicate_key(self):
        self.changed("d={'a':1,'a':2}\nresult=d.get('a')\n", "d['a']")

    def test_idempotent_after_extraction(self):
        result=self.changed("d={'x':1}\nresult=d.get('x')\n", "d['x']")
        self.assertEqual(result, transform(result))

    def test_skip_global_references(self):
        self.unchanged("global d\nd={'x':1}\nresult=d.get('x')\n")

    def test_skip_unsafe_computed_return(self):
        self.unchanged("d={'x':1}\nresult=f(d.get('x'))\n")

    def test_skip_reference_as_keyword(self):
        self.unchanged("d={'x':1}\nresult=f(value=d.get('x'))\n")

    def test_skip_nonadjacent_comment(self):
        self.unchanged("d={'x':1}\n# comment barrier\nresult=d.get('x')\n")

    def test_skip_mutating_subscript(self):
        self.unchanged("d={'x':1}\nresult=(d.get('x'),d.__setitem__('x',2))\n")

    def test_preserve_key_literal_quoting(self):
        self.changed('d={"hello":2}\nresult=d.get("hello")\n', 'd["hello"]')

    def test_skip_shadowed_dict_name_as_call(self):
        self.unchanged("def g():\n    d = factory()\n    return d.get('x')\nresult=g()\n")

    def test_skip_absent_previous_literal(self):
        self.unchanged("result=data.get('x')\n")

    def test_skip_wrong_keyword(self):
        self.unchanged("d={'x':1}\nresult=d.get(key='x')\n")


if __name__ == '__main__':
    unittest.main()
