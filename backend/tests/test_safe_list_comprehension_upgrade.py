"""Regression and conservative conversion tests for list comprehension styles."""

import ast
import contextlib
import io
import unittest

from app.services.improvement.safe_list_comprehension_service import (
    transform_for_append_to_list_comprehension as collapse,
    transform_list_comprehension_to_for_append as expand,
)


def _observe(source):
    scope = {"__name__": "__main__"}
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            exec(compile(source, "<comprehension-test>", "exec"), scope)
            exception = ("ok", "")
        except Exception as error:
            exception = (type(error).__name__, str(error))
    values = {name: repr(scope[name]) for name in ("result", "answer", "rows", "values", "total")
              if name in scope}
    leaks = sorted(key for key in scope if key.startswith("__capstone_"))
    return out.getvalue(), exception, values, leaks


def _equivalent(source, change, changed=True):
    output = change(source)
    ast.parse(output)
    assert (output != source) == changed, (source, output)
    before = _observe(source)
    after = _observe(output)
    assert before == after, (source, output, before, after)
    return output


class CollapseTests(unittest.TestCase):
    def test_basic(self):
        code = 'result = []\nfor item in [1, 2, 3]:\n    result.append(item * 2)\nprint(result)\n'
        result = _equivalent(code, collapse)
        self.assertIn('result = [item * 2 for item in [1, 2, 3]]', result)

    def test_filter(self):
        code = 'result = []\nfor i in range(10):\n    if i % 2 == 0:\n        result.append(i * i)\nprint(result)\n'
        output = _equivalent(code, collapse)
        self.assertIn(' if i % 2 == 0]', output)

    def test_two_nested_filters(self):
        code = 'result=[]\nfor x in (1,2,3,4):\n    if x > 1:\n        if x < 4:\n            result.append(x)\nprint(result)\n'
        _equivalent(code, collapse)

    def test_nested_function(self):
        code = 'def f(values):\n    result = []\n    for x in values:\n        result.append(x + 1)\n    return result\nprint(f([3,4]))\n'
        _equivalent(code, collapse)

    def test_empty_list(self):
        code = 'result=[]\nfor item in []:\n    result.append(item)\nprint(result)\n'
        _equivalent(code, collapse)

    def test_tuple_unpacking(self):
        code = 'result=[]\nfor x,y in [(1,2),(3,4)]:\n    result.append(x+y)\nprint(result)\n'
        _equivalent(code, collapse)

    def test_unicode(self):
        code = 'result=[]\nfor 글자 in "가나다":\n    result.append(글자 * 2)\nprint(result)\n'
        _equivalent(code, collapse)

    def test_preserve_comments_outside(self):
        code = '# before\nresult=[]\nfor x in [1]:\n    result.append(x)\n# after\nprint(result)\n'
        output = _equivalent(code, collapse)
        self.assertIn('# before', output)
        self.assertIn('# after', output)

    def test_multiple_pairs(self):
        code = 'result=[]\nfor x in [1,2]:\n    result.append(x+1)\nanswer=[]\nfor y in [3,4]:\n    answer.append(y+1)\nprint(result,answer)\n'
        output = _equivalent(code, collapse)
        self.assertEqual(output.count(' for '), 2)

    def test_skip_target_read_after_loop(self):
        code = 'result=[]\nfor x in [1,2]:\n    result.append(x)\nprint(x)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_target_used_before_loop(self):
        code = 'print(x)\nresult=[]\nfor x in [1,2]:\n    result.append(x)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_result_dependency_in_value(self):
        code = 'result=[]\nfor x in [1]:\n    result.append(result)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_result_dependency_in_iterator(self):
        code = 'result=[]\nfor x in result:\n    result.append(x)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_result_dependency_in_filter(self):
        code = 'result=[]\nfor x in [1]:\n    if result:\n        result.append(x)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_mutation_else(self):
        code = 'result=[]\nfor x in [1]:\n    result.append(x)\nelse:\n    print(1)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_multiple_body_statements(self):
        code = 'result=[]\nfor x in [1]:\n    print(x)\n    result.append(x)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_inline_comment(self):
        code = 'result=[] # important\nfor x in [1]:\n    result.append(x)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_loop_comment(self):
        code = 'result=[]\nfor x in [1]:\n    # important\n    result.append(x)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_user_function_call(self):
        code = 'result=[]\nfor x in [1]:\n    result.append(f(x))\n'
        self.assertEqual(collapse(code), code)

    def test_skip_locals(self):
        code = 'result=[]\nfor x in [1]:\n    result.append(x)\nprint(locals())\n'
        self.assertEqual(collapse(code), code)

    def test_range_supported(self):
        code = 'result=[]\nfor x in range(3):\n    result.append(x)\n'
        _equivalent(code, collapse)

    def test_skip_async(self):
        code = 'async def f(source):\n    result=[]\n    async for x in source:\n        result.append(x)\n    return result\n'
        self.assertEqual(collapse(code), code)

    def test_skip_break(self):
        code = 'result=[]\nfor x in [1]:\n    if x: break\n    result.append(x)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_continue(self):
        code = 'result=[]\nfor x in [1]:\n    if not x: continue\n    result.append(x)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_walrus(self):
        code = 'result=[]\nfor x in [1]:\n    result.append((y := x))\n'
        self.assertEqual(collapse(code), code)

    def test_skip_lambda(self):
        code = 'result=[]\nfor x in [1]:\n    result.append(lambda: x)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_semi_neighbor(self):
        code = 'a=5; result=[]\nfor x in [1]:\n    result.append(x)\n'
        self.assertEqual(collapse(code), code)

    def test_syntax_invalid_unchanged(self):
        code = 'for item in [1:\n    pass'
        self.assertEqual(collapse(code), code)

    def test_no_match(self):
        code = 'result=[1]\nfor x in [2]:\n    result.append(x)\n'
        self.assertEqual(collapse(code), code)


class ExpandTests(unittest.TestCase):
    def test_basic(self):
        code = 'result = [x * 2 for x in [1, 2, 3]]\nprint(result)\n'
        output = _equivalent(code, expand)
        self.assertIn('for __capstone_list_item_', output)
        self.assertIn('.append(', output)

    def test_filter(self):
        code = 'result=[x for x in [1, 2, 3] if x>1]\nprint(result)\n'
        _equivalent(code, expand)

    def test_two_filters(self):
        code = 'result=[x for x in [1, 2, 3] if x>1 if x<3]\nprint(result)\n'
        _equivalent(code, expand)

    def test_unicode(self):
        code = 'result=[글자*2 for 글자 in "가나"]\nprint(result)\n'
        _equivalent(code, expand)

    def test_empty_list(self):
        code = 'result=[x for x in []]\nprint(result)\n'
        _equivalent(code, expand)

    def test_nested_function(self):
        code = 'def f(seq):\n    result=[x+1 for x in seq]\n    return result\nprint(f([1,2]))\n'
        _equivalent(code, expand)

    def test_unpacking(self):
        code = 'result=[x+y for x,y in [(1,2),(3,4)]]\nprint(result)\n'
        _equivalent(code, expand)

    def test_existing_loop_target(self):
        code = 'x="unchanged"\nresult=[x for x in [1,2]]\nprint(x,result)\n'
        _equivalent(code, expand)

    def test_source_uses_existing_result(self):
        code = 'result=[1,2]\nresult=[x+1 for x in result]\nprint(result)\n'
        _equivalent(code, expand)

    def test_source_uses_outer_same_name(self):
        code = 'x=[1,2]\nresult=[x for x in x]\nprint(result,x)\n'
        _equivalent(code, expand)

    def test_no_extra_temp_var(self):
        code = 'result=[x for x in [1,2]]\n'
        _equivalent(code, expand)

    def test_collision_generated_var(self):
        code = '__capstone_list_item_0 = 5\nresult=[x*2 for x in [1]]\nprint(__capstone_list_item_0,result)\n'
        output = _equivalent(code, expand)
        self.assertIn('for __capstone_list_item_1', output)

    def test_two_assignments(self):
        code = 'result=[x for x in [1,2]]\nanswer=[y+2 for y in [3,4]]\nprint(result,answer)\n'
        _equivalent(code, expand)

    def test_preserve_comments_outside(self):
        code = '# before\nresult=[x for x in [1,2]]\n# after\nprint(result)\n'
        output = _equivalent(code, expand)
        self.assertIn('# before', output)
        self.assertIn('# after', output)

    def test_old_result_unchanged_on_exception(self):
        code = 'result=[42]\nresult=[10 // x for x in [2,0]]\n'
        _equivalent(code, expand)

    def test_existing_result_unchanged_on_iterator_error(self):
        code = 'class Broken:\n    def __iter__(self):\n        raise ValueError("bad")\nresult=[42]\nresult=[x for x in Broken()]\n'
        self.assertEqual(expand(code), code)

    def test_invalid_element_type_error(self):
        code = 'result=[x+1 for x in [1,"a"]]\n'
        _equivalent(code, expand)

    def test_unpacked_mismatch_exception(self):
        code = 'result=[x+y for x,y in [(1,2),(3,)]]\n'
        _equivalent(code, expand)

    def test_multiple_comments(self):
        code = '# comment1\nresult=[x for x in [1]]\n# comment2\nprint(result)\n# comment3\n'
        _equivalent(code, expand)

    def test_skip_inline_comment(self):
        code = 'result=[x for x in [1]] # comment\n'
        self.assertEqual(expand(code), code)

    def test_skip_multigenerator(self):
        code = 'result=[(x,y) for x in [1] for y in [2]]\n'
        self.assertEqual(expand(code), code)

    def test_skip_async_comprehension(self):
        code = 'async def f(xs):\n    result=[x async for x in xs]\n    return result\n'
        self.assertEqual(expand(code), code)

    def test_skip_user_call(self):
        code = 'result=[str(x) for x in [1,2]]\n'
        self.assertEqual(expand(code), code)

    def test_skip_walrus(self):
        code = 'result=[(y := x) for x in [1]]\n'
        self.assertEqual(expand(code), code)

    def test_skip_lambda(self):
        code = 'result=[lambda: x for x in [1]]\n'
        self.assertEqual(expand(code), code)

    def test_skip_introspection(self):
        code = 'result=[x for x in [1]]\nprint(vars())\n'
        self.assertEqual(expand(code), code)

    def test_skip_nested_comprehension(self):
        code = 'result=[[y for y in [x]] for x in [1,2]]\n'
        self.assertEqual(expand(code), code)

    def test_skip_return(self):
        code = 'def f():\n    return [x for x in [1,2]]\n'
        self.assertEqual(expand(code), code)

    def test_skip_assignment_chain(self):
        code = 'result=other=[x for x in [1,2]]\n'
        self.assertEqual(expand(code), code)

    def test_skip_adjacent_semicolon(self):
        code = 'result=[x for x in [1,2]]; print(result)\n'
        self.assertEqual(expand(code), code)

    def test_invalid_code(self):
        code = 'result = [x for x in [1,2]\n'
        self.assertEqual(expand(code), code)

    def test_keep_already_explicit(self):
        code = 'result=[]\nfor x in [1]:\n    result.append(x)\n'
        self.assertEqual(expand(code), code)

    def test_non_list_comprehensions_unchanged(self):
        code = 'result={x for x in [1,2]}\n'
        self.assertEqual(expand(code), code)


class RoundTripTests(unittest.TestCase):
    def test_simple_roundtrip_semantics(self):
        source = 'result=[]\nfor x in [1,2,3]:\n    result.append(x * 2)\nprint(result)\n'
        output = expand(collapse(source))
        self.assertNotEqual(output, source)
        self.assertEqual(_observe(source), _observe(output))

    def test_condition_roundtrip_semantics(self):
        source = 'result=[]\nfor x in [1,2,3]:\n    if x > 1:\n        result.append(x * 3)\nprint(result)\n'
        output = expand(collapse(source))
        self.assertEqual(_observe(source), _observe(output))

    def test_crlf_preserved(self):
        source = 'result=[]\r\nfor x in [1,2]:\r\n    result.append(x)\r\nprint(result)\r\n'
        output = collapse(source)
        self.assertIn('\r\nprint(result)', output)
        self.assertEqual(_observe(source), _observe(output))

    def test_expand_range(self):
        source = 'result=[x for x in range(5) if x>2]\nprint(result)\n'
        _equivalent(source, expand)

    def test_reject_shadowed_range(self):
        source = 'range = lambda x: [1]\nresult=[x for x in range(3)]\n'
        self.assertEqual(expand(source), source)

    def test_expanded_code_is_idempotent(self):
        source = 'result=[x*2 for x in [1,2]]\n'
        output = expand(source)
        self.assertEqual(expand(output), output)

    def test_collapsed_code_is_idempotent(self):
        source = 'result=[]\nfor x in [1,2]:\n    result.append(x)\n'
        output = collapse(source)
        self.assertEqual(collapse(output), output)


if __name__ == '__main__':
    unittest.main()
