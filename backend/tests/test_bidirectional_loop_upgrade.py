"""Functional and negative tests for both loop-conversion directions."""

import ast
import contextlib
import io
import unittest

from app.services.improvement.iteration_style_service import (
    transform_to_while_iteration_style,
    transform_to_direct_iteration_style,
    transform_to_index_iteration_style,
)
from app.services.improvement.counted_while_to_for_service import (
    transform_counted_while_to_for,
)


def _observe(source):
    scope = {"__name__": "__main__"}
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            exec(compile(source, "<loop-test>", "exec"), scope)
            outcome = ("ok", "")
        except Exception as error:
            outcome = (type(error).__name__, str(error))
    selected = {
        name: scope[name]
        for name in ("i", "j", "n", "item", "values", "result", "total", "output")
        if name in scope
    }
    return out.getvalue(), outcome, selected


def _equivalent(source, transform):
    changed = transform(source)
    ast.parse(changed)
    before = _observe(source)
    after = _observe(changed)
    assert before == after, (source, changed, before, after)
    return changed


class ForToWhileTests(unittest.TestCase):
    def test_basic_list(self):
        code = 'for item in [10, 20, 30]:\n    print(item)\n'
        result = _equivalent(code, transform_to_while_iteration_style)
        self.assertIn("while True:", result)

    def test_range_and_last_index(self):
        code = 'for i in range(5):\n    print(i)\nprint(i)\n'
        _equivalent(code, transform_to_while_iteration_style)

    def test_continue(self):
        code = '''for i in range(5):
    if i == 2:
        continue
    print(i)
print(i)
'''
        _equivalent(code, transform_to_while_iteration_style)

    def test_break(self):
        code = '''for i in range(5):
    if i == 3:
        break
    print(i)
print(i)
'''
        _equivalent(code, transform_to_while_iteration_style)

    def test_for_else_exhaustion(self):
        code = 'for item in [1, 2]:\n    print(item)\nelse:\n    print("done")\n'
        result = _equivalent(code, transform_to_while_iteration_style)
        self.assertIn("if __capstone_finished_", result)

    def test_for_else_break(self):
        code = '''for item in [1, 2]:
    if item == 1:
        break
else:
    print("never")
print(item)
'''
        _equivalent(code, transform_to_while_iteration_style)

    def test_for_else_continue(self):
        code = '''for item in [1, 2]:
    if item == 1:
        continue
else:
    print("finished")
'''
        _equivalent(code, transform_to_while_iteration_style)

    def test_tuple_unpacking(self):
        code = 'for i, j in [(1, 2), (3, 4)]:\n    print(i + j)\n'
        _equivalent(code, transform_to_while_iteration_style)

    def test_string(self):
        code = 'for item in "abc":\n    print(item)\n'
        _equivalent(code, transform_to_while_iteration_style)

    def test_generator_expression(self):
        code = 'for item in (i * 2 for i in range(4)):\n    print(item)\n'
        _equivalent(code, transform_to_while_iteration_style)

    def test_list_mutation_during_iteration(self):
        code = '''values = [1, 2]
for item in values:
    print(item)
    if item < 4:
        values.append(item + 1)
print(values)
'''
        _equivalent(code, transform_to_while_iteration_style)

    def test_empty_iterator_and_no_variable(self):
        code = 'for item in []:\n    print(item)\nprint(item)\n'
        _equivalent(code, transform_to_while_iteration_style)

    def test_nested_scope(self):
        code = '''def calculate(n):
    total = 0
    for i in range(n):
        total += i
    return total
print(calculate(5))
'''
        _equivalent(code, transform_to_while_iteration_style)

    def test_stop_iteration_from_assignment_is_not_swallowed(self):
        code = ("class Target:\n"
                "    def __setitem__(self, key, value):\n"
                "        raise StopIteration('from-target')\n"
                "target = Target()\n"
                "for target[0] in [1, 2]:\n"
                "    print('never')\n")
        _equivalent(code, transform_to_while_iteration_style)

    def test_preserve_comments_outside(self):
        code = '# before\nfor item in [1, 2]:\n    print(item)\n# after\n'
        result = _equivalent(code, transform_to_while_iteration_style)
        self.assertIn('# before', result)
        self.assertIn('# after', result)

    def test_skip_comments_inside(self):
        code = 'for item in [1, 2]:\n    # important\n    print(item)\n'
        self.assertEqual(transform_to_while_iteration_style(code), code)

    def test_skip_shadowed_next(self):
        code = 'next = 5\nfor item in [1, 2]:\n    print(item)\n'
        self.assertEqual(transform_to_while_iteration_style(code), code)

    def test_skip_introspection(self):
        code = 'for item in [1, 2]:\n    print(locals())\n'
        self.assertEqual(transform_to_while_iteration_style(code), code)

    def test_preserve_direct_index_actions(self):
        before = 'values = [1, 2]\nfor i in range(len(values)):\n    print(values[i])\n'
        self.assertIn('for item in values:', transform_to_direct_iteration_style(before))
        before = 'values = [1, 2]\nfor item in values:\n    print(item)\n'
        self.assertIn('for index in range(len(values)):', transform_to_index_iteration_style(before))


class RoundTripTests(unittest.TestCase):
    def test_for_range_while_back_to_for(self):
        source = 'for i in range(4):\n    print(i)\nprint(i)\n'
        middle = transform_to_while_iteration_style(source)
        restored = transform_counted_while_to_for(middle)
        self.assertEqual(ast.dump(ast.parse(source)), ast.dump(ast.parse(restored)))
        self.assertEqual(_observe(source), _observe(restored))

    def test_for_else_break_round_trip(self):
        source = 'for i in range(4):\n    if i == 2: break\nelse:\n    print("done")\n'
        middle = transform_to_while_iteration_style(source)
        restored = transform_counted_while_to_for(middle)
        self.assertEqual(ast.dump(ast.parse(source)), ast.dump(ast.parse(restored)))
        self.assertEqual(_observe(source), _observe(restored))

    def test_nested_function_round_trip(self):
        source = 'def f(items):\n    for item in items:\n        print(item)\n    return 1\nprint(f([1,2]))\n'
        middle = transform_to_while_iteration_style(source)
        restored = transform_counted_while_to_for(middle)
        self.assertEqual(ast.dump(ast.parse(source)), ast.dump(ast.parse(restored)))
        self.assertEqual(_observe(source), _observe(restored))


class WhileToForTests(unittest.TestCase):
    def test_basic_counted(self):
        code = 'i = 0\nwhile i < 5:\n    print(i)\n    i += 1\nprint(i)\n'
        result = _equivalent(code, transform_counted_while_to_for)
        self.assertIn('for i in range(i, 5):', result)

    def test_inclusive_counted(self):
        code = 'i = 0\nwhile i <= 5:\n    print(i)\n    i += 2\nprint(i)\n'
        _equivalent(code, transform_counted_while_to_for)

    def test_decreasing(self):
        code = 'i = 10\nwhile i > 0:\n    print(i)\n    i -= 3\nprint(i)\n'
        _equivalent(code, transform_counted_while_to_for)

    def test_reversed_bound(self):
        code = 'i = 10\nwhile 0 < i:\n    print(i)\n    i = i - 3\n'
        _equivalent(code, transform_counted_while_to_for)

    def test_variable_bound_with_integer_declaration(self):
        code = 'limit = 5\ni = 0\nwhile i < limit:\n    print(i)\n    i = 1 + i\n'
        result = _equivalent(code, transform_counted_while_to_for)
        self.assertIn('for i in range(i, limit):', result)

    def test_static_list_length(self):
        code = 'values = [10, 20, 30]\ni = 0\nwhile i < len(values):\n    print(values[i])\n    i += 1\n'
        result = _equivalent(code, transform_counted_while_to_for)
        self.assertIn('for i in range(i, len(values)):', result)

    def test_break(self):
        code = '''i = 0
while i < 10:
    if i == 4:
        break
    print(i)
    i += 1
print(i)
'''
        _equivalent(code, transform_counted_while_to_for)

    def test_while_else(self):
        code = 'i = 0\nwhile i < 3:\n    print(i)\n    i += 1\nelse:\n    print("end")\n'
        _equivalent(code, transform_counted_while_to_for)

    def test_zero_iterations(self):
        code = 'i = 10\nwhile i < 2:\n    print(i)\n    i += 1\nprint(i)\n'
        _equivalent(code, transform_counted_while_to_for)

    def test_skip_unproven_counter(self):
        code = 'def count(i):\n    while i < 5:\n        print(i)\n        i += 1\n'
        self.assertEqual(transform_counted_while_to_for(code), code)

    def test_skip_unproven_bound(self):
        code = 'i = 0\nlimit = 2.5\nwhile i < limit:\n    print(i)\n    i += 1\n'
        self.assertEqual(transform_counted_while_to_for(code), code)

    def test_skip_mutating_list_length(self):
        code = 'values = [1]\ni = 0\nwhile i < len(values):\n    values.append(i)\n    i += 1\n'
        self.assertEqual(transform_counted_while_to_for(code), code)

    def test_skip_aliased_mutable_bound(self):
        code = 'values = [1, 2]\nalias = values\ni = 0\nwhile i < len(values):\n    alias.append(i)\n    i += 1\n'
        self.assertEqual(transform_counted_while_to_for(code), code)

    def test_skip_continue(self):
        code = 'i = 0\nwhile i < 5:\n    if i == 2:\n        continue\n    i += 1\n'
        self.assertEqual(transform_counted_while_to_for(code), code)

    def test_skip_unbounded(self):
        code = 'while True:\n    print(1)\n    break\n'
        self.assertEqual(transform_counted_while_to_for(code), code)

    def test_skip_wrong_direction(self):
        code = 'i = 0\nwhile i > 5:\n    print(i)\n    i += 1\n'
        self.assertEqual(transform_counted_while_to_for(code), code)

    def test_no_change_for_loops(self):
        code = 'for i in range(5):\n    print(i)\n'
        self.assertEqual(transform_counted_while_to_for(code), code)

    def test_unicode_comments(self):
        code = 'i = 0\nwhile i < 2: # 한국어: 주석\n    print(i)\n    i += 1\n'
        _equivalent(code, transform_counted_while_to_for)


if __name__ == '__main__':
    unittest.main()
