"""Standalone unit tests for safe dictionary-comprehension conversions."""

import ast
import contextlib
import io
import unittest

from app.services.improvement.safe_dict_comprehension_service import (
    transform_dict_comprehension_to_for_assignment as expand,
    transform_for_assignment_to_dict_comprehension as collapse,
)


def _observe(source):
    scope = {'__name__': '__main__'}
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        try:
            exec(compile(source, '<dict-comprehension-test>', 'exec'), scope)
            status = 'ok', ''
        except Exception as exc:
            status = type(exc).__name__, str(exc)
    visible = {
        name: scope[name]
        for name in ('result', 'before', 'values', 'items', 'other', 'total', 'answer',
                     '__capstone_dict_result_0', 'target', 'source')
        if name in scope
    }
    return buffer.getvalue(), status, visible


def _eq(source, transform):
    candidate = transform(source)
    ast.parse(candidate)
    assert _observe(source) == _observe(candidate), (source, candidate, _observe(source), _observe(candidate))
    return candidate


class CollapseTests(unittest.TestCase):
    def test_basic(self):
        code = 'result = {}\nfor x in [1, 2, 3]:\n    result[x] = x * 2\nprint(result)\n'
        self.assertIn('{x: x * 2 for x in [1, 2, 3]}', _eq(code, collapse))

    def test_filter(self):
        code = 'result = {}\nfor x in [1, 2, 3, 4]:\n    if x % 2 == 0:\n        result[x] = x ** 2\nprint(result)\n'
        self.assertIn('if x % 2 == 0', _eq(code, collapse))

    def test_nested_filters(self):
        code = 'result = {}\nfor x in [1, 2, 3, 4]:\n    if x > 1:\n        if x < 4:\n            result[x] = x * 10\nprint(result)\n'
        self.assertIn('if x > 1 if x < 4', _eq(code, collapse))

    def test_duplicate_keys(self):
        code = 'result = {}\nfor x in [1, 1, 2]:\n    result[x] = x + 8\nprint(result)\n'
        _eq(code, collapse)

    def test_empty(self):
        code = 'result = {}\nfor x in []:\n    result[x] = x\nprint(result)\n'
        _eq(code, collapse)

    def test_tuple_unpack(self):
        code = 'result = {}\nfor x, v in [(1, 3), (2, 4)]:\n    result[x] = v\nprint(result)\n'
        _eq(code, collapse)

    def test_range(self):
        code = 'result = {}\nfor x in range(3):\n    result[x] = x + 1\nprint(result)\n'
        _eq(code, collapse)

    def test_range_negative(self):
        code = 'result = {}\nfor x in range(-3, -1):\n    result[x] = x\n'
        self.assertIn('for x in range(-3, -1)', _eq(code, collapse))

    def test_string_source(self):
        code = 'result = {}\nfor x in "abc":\n    result[x] = x\n'
        _eq(code, collapse)

    def test_boolean_values(self):
        code = 'result = {}\nfor x in (True, False):\n    result[x] = not x\n'
        _eq(code, collapse)

    def test_unicode_source(self):
        code = '# 앞\nresult = {}\nfor x in "가나":\n    result[x] = x\n# 뒤\n'
        transformed = _eq(code, collapse)
        self.assertIn('# 앞', transformed)
        self.assertIn('# 뒤', transformed)

    def test_nested_function(self):
        code = 'def f():\n    result = {}\n    for x in (1, 2):\n        result[x] = 2 * x\n    return result\nprint(f())\n'
        _eq(code, collapse)

    def test_multiple_pairs(self):
        code = 'result = {}\nfor x in (1, 2):\n    result[x] = x\nother = {}\nfor v in (3, 4):\n    other[v] = v * v\nprint(result, other)\n'
        transformed = _eq(code, collapse)
        self.assertEqual(transformed.count('for x in'), 1)
        self.assertEqual(transformed.count('for v in'), 1)
        self.assertIn('other = {v: v * v', transformed)

    def test_preserve_unrelated_comment(self):
        code = '# comment\nresult = {}\nfor x in (1, 2):\n    result[x] = x\n# after\n'
        transformed = _eq(code, collapse)
        self.assertIn('# comment', transformed)
        self.assertIn('# after', transformed)

    def test_skip_break(self):
        code = 'result = {}\nfor x in (1, 2):\n    if x == 2: break\n    result[x] = x\n'
        self.assertEqual(collapse(code), code)

    def test_skip_continue(self):
        code = 'result = {}\nfor x in (1, 2):\n    if x == 2: continue\n    result[x] = x\n'
        self.assertEqual(collapse(code), code)

    def test_skip_else(self):
        code = 'result = {}\nfor x in (1, 2):\n    result[x] = x\nelse:\n    print("complete")\n'
        self.assertEqual(collapse(code), code)

    def test_skip_conditional_else(self):
        code = 'result = {}\nfor x in (1, 2):\n    if x:\n        result[x] = x\n    else:\n        result[0] = 0\n'
        self.assertEqual(collapse(code), code)

    def test_skip_result_depends_on_result(self):
        code = 'result = {}\nfor x in (1, 2):\n    result[x] = len(result)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_result_depends_on_key(self):
        code = 'result = {}\nfor x in (1, 2):\n    result[len(result)] = x\n'
        self.assertEqual(collapse(code), code)

    def test_skip_result_depends_on_iterator(self):
        code = 'result = {}\nfor x in result:\n    result[x] = x\n'
        self.assertEqual(collapse(code), code)

    def test_skip_result_depends_on_filter(self):
        code = 'result = {}\nfor x in [1]:\n    if result:\n        result[x] = x\n'
        self.assertEqual(collapse(code), code)

    def test_skip_target_read_after(self):
        code = 'result = {}\nfor x in (1, 2):\n    result[x] = x\nprint(x)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_target_read_before(self):
        code = 'x = 9\nresult = {}\nfor x in (1, 2):\n    result[x] = x\n'
        self.assertEqual(collapse(code), code)

    def test_skip_self_target(self):
        code = 'result = {}\nfor result in ({}, {}):\n    result[0] = 3\n'
        self.assertEqual(collapse(code), code)

    def test_skip_comments_inside(self):
        code = 'result = {}\nfor x in (1, 2):\n    # do not lose this\n    result[x] = x\n'
        self.assertEqual(collapse(code), code)

    def test_skip_inline_comment(self):
        code = 'result = {}\nfor x in (1, 2):\n    result[x] = x  # important\n'
        self.assertEqual(collapse(code), code)

    def test_skip_comment_at_init(self):
        code = 'result = {}  # alias\nfor x in (1, 2):\n    result[x] = x\n'
        self.assertEqual(collapse(code), code)

    def test_skip_multiple_statements(self):
        code = 'result = {}\nfor x in (1, 2):\n    result[x] = x\n    print(x)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_dict_not_empty(self):
        code = 'result = {0: 0}\nfor x in (1, 2):\n    result[x] = x\n'
        self.assertEqual(collapse(code), code)

    def test_skip_dict_constructor(self):
        code = 'result = dict()\nfor x in (1, 2):\n    result[x] = x\n'
        self.assertEqual(collapse(code), code)

    def test_skip_set(self):
        code = 'result = set()\nfor x in (1, 2):\n    result.add(x)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_subscript_read_call(self):
        code = 'result = {}\nfor x in (1, 2):\n    result[x] = lookup[x]\n'
        self.assertEqual(collapse(code), code)

    def test_skip_call_in_value(self):
        code = 'result = {}\nfor x in (1, 2):\n    result[x] = f(x)\n'
        self.assertEqual(collapse(code), code)

    def test_skip_call_in_filter(self):
        code = 'result = {}\nfor x in (1, 2):\n    if check(x):\n        result[x] = x\n'
        self.assertEqual(collapse(code), code)

    def test_skip_lambda(self):
        code = 'result = {}\nfor x in (1, 2):\n    result[x] = lambda: x\n'
        self.assertEqual(collapse(code), code)

    def test_skip_nested_comprehension(self):
        code = 'result = {}\nfor x in (1, 2):\n    result[x] = [v for v in (1, 2)]\n'
        self.assertEqual(collapse(code), code)

    def test_skip_range_shadowing(self):
        code = 'range = lambda n: [n]\nresult = {}\nfor x in range(3):\n    result[x] = x\n'
        self.assertEqual(collapse(code), code)

    def test_skip_introspection(self):
        code = 'result = {}\nfor x in (1, 2):\n    result[x] = x\nprint(locals())\n'
        self.assertEqual(collapse(code), code)

    def test_skip_semicolon(self):
        code = 'result = {}; print("start")\nfor x in (1, 2):\n    result[x] = x\n'
        self.assertEqual(collapse(code), code)

    def test_skip_class_body(self):
        code = 'class C:\n    result = {}\n    for x in (1, 2):\n        result[x] = x\n'
        self.assertEqual(collapse(code), code)

    def test_skip_invalid_code(self):
        code = 'result = {\n'
        self.assertEqual(collapse(code), code)

    def test_skip_async_loop(self):
        code = 'async def f(items):\n    result = {}\n    async for x in items:\n        result[x] = x\n'
        self.assertEqual(collapse(code), code)


class ExpandTests(unittest.TestCase):
    def test_basic(self):
        code = 'result = {x: x * 2 for x in (1, 2, 3)}\nprint(result)\n'
        lowered = _eq(code, expand)
        self.assertIn('for __capstone_dict_item_', lowered)

    def test_conditional(self):
        code = 'result = {x: x * x for x in (1, 2, 3, 4) if x % 2 == 0}\n'
        _eq(code, expand)

    def test_two_filters(self):
        code = 'result = {x: x for x in (1, 2, 3, 4) if x > 1 if x < 4}\n'
        _eq(code, expand)

    def test_tuple_unpack(self):
        code = 'result = {x: v * 2 for x, v in [(1, 2), (3, 4)]}\nprint(result)\n'
        _eq(code, expand)

    def test_generator_empty(self):
        code = 'result = {x: x for x in []}\nprint(result)\n'
        _eq(code, expand)

    def test_bool_value(self):
        code = 'result = {x: x >= 2 for x in (1, 2)}\n'
        _eq(code, expand)

    def test_range(self):
        code = 'result = {x: x * x for x in range(5)}\n'
        _eq(code, expand)

    def test_negative_range(self):
        code = 'result = {x: -x for x in range(-2, 2)}\n'
        _eq(code, expand)

    def test_unicode(self):
        code = '# 시작\nresult = {x: x for x in "한국"}\n# 끝\n'
        result = _eq(code, expand)
        self.assertIn('# 시작', result)
        self.assertIn('# 끝', result)

    def test_existing_old_result(self):
        code = 'result = {"old": 99}\nresult = {x: x for x in (1, 2)}\n'
        _eq(code, expand)

    def test_original_binding_on_key_error(self):
        code = 'result = {"old": 99}\nresult = {x: x for x in [[1]]}\n'
        lowered = _eq(code, expand)
        self.assertNotIn('result = {}', lowered)

    def test_original_binding_on_unpack_error(self):
        code = 'result = {"old": 99}\nresult = {x: v for x, v in [(1, 2), (3,)]}\n'
        _eq(code, expand)

    def test_existing_outer_x(self):
        code = 'x = "prior"\nresult = {x: x for x in (1, 2)}\nprint(x, result)\n'
        _eq(code, expand)

    def test_no_generated_name_leak(self):
        code = 'result = {x: x for x in (1, 2)}\nprint(result)\n'
        lowered = _eq(code, expand)
        self.assertIn('finally:', lowered)
        self.assertIn('del __capstone_dict_result_', lowered)

    def test_name_collision(self):
        code = '__capstone_dict_result_0 = 9\nresult = {x: x for x in (1, 2)}\n'
        lowered = _eq(code, expand)
        self.assertIn('__capstone_dict_result_1', lowered)

    def test_existing_loop_target_does_not_leak(self):
        code = 'x = 100\nresult = {x: 2*x for x in (1, 2)}\nprint(x)\n'
        _eq(code, expand)

    def test_function(self):
        code = 'def calc():\n    result = {x: x + 1 for x in (1, 2)}\n    return result\nprint(calc())\n'
        _eq(code, expand)

    def test_multiple_assignments(self):
        code = 'result = {x: x for x in (1, 2)}\nother = {v: v**2 for v in (3, 4)}\nprint(result, other)\n'
        lowered = _eq(code, expand)
        self.assertEqual(lowered.count('finally:'), 2)

    def test_preserve_outside_comments(self):
        code = '# before\nresult = {x: x for x in (1, 2)}\n# after\n'
        result = _eq(code, expand)
        self.assertIn('# before', result)
        self.assertIn('# after', result)

    def test_skip_comment_inline(self):
        code = 'result = {x: x for x in (1, 2)}  # keep\n'
        self.assertEqual(expand(code), code)

    def test_skip_invalid(self):
        code = 'result = {x: for x in (1, 2)}\n'
        self.assertEqual(expand(code), code)

    def test_skip_chain_assign(self):
        code = 'a = result = {x: x for x in (1, 2)}\n'
        self.assertEqual(expand(code), code)

    def test_skip_return(self):
        code = 'def f():\n    return {x: x for x in (1, 2)}\n'
        self.assertEqual(expand(code), code)

    def test_skip_mixed_nested_generator(self):
        code = 'result = {(x, v): x * v for x in (1, 2) for v in (3, 4)}\n'
        self.assertEqual(expand(code), code)

    def test_skip_async_comp(self):
        code = 'async def f(items):\n    result = {x: x async for x in items}\n'
        self.assertEqual(expand(code), code)

    def test_skip_lambda(self):
        code = 'result = {x: lambda: x for x in (1, 2)}\n'
        self.assertEqual(expand(code), code)

    def test_skip_call(self):
        code = 'result = {x: f(x) for x in (1, 2)}\n'
        self.assertEqual(expand(code), code)

    def test_skip_subscript(self):
        code = 'result = {x: values[x] for x in (1, 2)}\n'
        self.assertEqual(expand(code), code)

    def test_skip_introspection(self):
        code = 'result = {x: x for x in (1, 2)}\nprint(locals())\n'
        self.assertEqual(expand(code), code)

    def test_skip_walrus(self):
        code = 'result = {x: (v := x) for x in (1, 2)}\n'
        self.assertEqual(expand(code), code)

    def test_skip_range_shadowed(self):
        code = 'range = lambda n: [n]\nresult = {x: x for x in range(3)}\n'
        self.assertEqual(expand(code), code)

    def test_skip_class_body(self):
        code = 'class C:\n    y = 2\n    result = {x: x + y for x in (1, 2)}\n'
        self.assertEqual(expand(code), code)

    def test_skip_semicolon(self):
        code = 'result = {x: x for x in (1, 2)}; print("hi")\n'
        self.assertEqual(expand(code), code)

    def test_skip_already_explicit(self):
        code = 'result = {}\nfor x in (1, 2):\n    result[x] = x\n'
        self.assertEqual(expand(code), code)

    def test_skip_attribute(self):
        code = 'result = {x: obj.attr for x in (1, 2)}\n'
        self.assertEqual(expand(code), code)

    def test_skip_nested_comprehension(self):
        code = 'result = {x: [v for v in (1, 2)] for x in (1, 2)}\n'
        self.assertEqual(expand(code), code)


class RoundTripTests(unittest.TestCase):
    def test_expand_is_stable(self):
        code = 'result = {x: x + 1 for x in (1, 2)}\n'
        self.assertEqual(expand(expand(code)), expand(code))

    def test_collapse_is_stable(self):
        code = 'result = {}\nfor x in (1, 2):\n    result[x] = x\n'
        self.assertEqual(collapse(collapse(code)), collapse(code))

    def test_same_output_after_collapse(self):
        code = 'result = {}\nfor x in (1, 2, 3):\n    if x > 1:\n        result[x] = x * x\n'
        _eq(code, collapse)

    def test_same_output_after_expansion(self):
        code = 'result = {x: x * x for x in (1, 2, 3) if x > 1}\n'
        _eq(code, expand)

    def test_crlf_preserved(self):
        code = 'result = {}\r\nfor x in (1, 2):\r\n    result[x] = x\r\n'
        lowered = _eq(code, collapse)
        self.assertIn('\r\n', lowered)

    def test_multiple_vars_roundtrip(self):
        code = 'result = {}\nfor x, v in [(1, 2), (2, 3)]:\n    result[x] = v\n'
        result = collapse(code)
        self.assertIn('{x: v for x, v in', result)
        self.assertEqual(_observe(code), _observe(expand(result)))


if __name__ == '__main__':
    unittest.main()
