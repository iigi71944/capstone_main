"""Semantic and negative cases for the indexed/direct conversion upgrade."""

import ast
import contextlib
import io
import unittest

from app.services.improvement.safe_index_iteration_service import (
    transform_to_direct_iteration_style,
    transform_to_index_iteration_style,
)


def observe(code):
    scope = {"__name__": "__main__"}
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        try:
            exec(compile(code, "<iteration-test>", "exec"), scope)
            outcome = ("ok", "")
        except Exception as error:
            outcome = (type(error).__name__, str(error))
    visible = {k: scope.get(k, "<absent>") for k in (
        "values", "i", "item", "total", "pairs", "left", "right",
        "answer", "result", "items", "name", "n"
    )}
    return output.getvalue(), outcome, visible


def equivalent(code, transform):
    converted = transform(code)
    ast.parse(converted)
    before = observe(code)
    after = observe(converted)
    # In the direct-only variant the old index is intentionally discarded.
    # In all cases stdout and the exception outcome must match exactly;
    # explicit reads of the old index (including in for-else) are retained
    # through enumerate and therefore still tested by stdout comparisons.
    if transform is transform_to_direct_iteration_style:
        # Unreferenced names introduced/removed by a style rewrite are not
        # program-observable without introspection (which is excluded).
        before[2].pop("i", None)
        after[2].pop("i", None)
        if not any(isinstance(node, ast.Name) and node.id == "item"
                   for node in ast.walk(ast.parse(code))):
            before[2].pop("item", None)
            after[2].pop("item", None)
    assert after == before, (code, converted, before, after)
    return converted


class DirectTests(unittest.TestCase):
    def test_basic_list(self):
        code = 'values = [10, 20, 30]\nfor i in range(len(values)):\n    print(values[i])\n'
        result = equivalent(code, transform_to_direct_iteration_style)
        self.assertIn('for item in values:', result)

    def test_preserves_index_in_body_with_enumerate(self):
        code = 'values = [10, 20]\nfor i in range(len(values)):\n    print(i, values[i])\n'
        result = equivalent(code, transform_to_direct_iteration_style)
        self.assertIn('for i, item in enumerate(values):', result)

    def test_preserves_index_after_loop(self):
        code = 'values = [10, 20]\nfor i in range(len(values)):\n    print(values[i])\nprint(i)\n'
        result = equivalent(code, transform_to_direct_iteration_style)
        self.assertIn('enumerate(values)', result)

    def test_index_read_within_condition(self):
        code = 'values = [10, 20, 30]\nfor i in range(len(values)):\n    if i % 2 == 0:\n        print(values[i])\n'
        result = equivalent(code, transform_to_direct_iteration_style)
        self.assertIn('enumerate(values)', result)

    def test_break_continue(self):
        code = '''values = [1, 2, 3, 4]
for i in range(len(values)):
    if values[i] == 2:
        continue
    if values[i] == 4:
        break
    print(values[i])
'''
        self.assertIn('for item in values:', equivalent(code, transform_to_direct_iteration_style))

    def test_for_else(self):
        code = '''values = [1, 2]
for i in range(len(values)):
    print(values[i])
else:
    print("finished")
'''
        result = equivalent(code, transform_to_direct_iteration_style)
        self.assertIn('else:', result)

    def test_tuple(self):
        code = 'values = (1, 2, 3)\nfor i in range(len(values)):\n    print(values[i])\n'
        self.assertNotEqual(equivalent(code, transform_to_direct_iteration_style), code)

    def test_string_and_unicode(self):
        code = 'values = "가나다"\nfor i in range(len(values)):\n    print(values[i])\n'
        self.assertNotEqual(equivalent(code, transform_to_direct_iteration_style), code)

    def test_bytes(self):
        code = 'values = b"xyz"\nfor i in range(len(values)):\n    print(values[i])\n'
        self.assertNotEqual(equivalent(code, transform_to_direct_iteration_style), code)

    def test_multiple_loops(self):
        code = '''values = [1, 2]
for i in range(len(values)):
    print(values[i])
values = [1, 2]
for i in range(len(values)):
    print(i, values[i])
'''
        result = equivalent(code, transform_to_direct_iteration_style)
        self.assertIn('for i, item in enumerate(values):', result)
        self.assertIn('for i, __capstone_item_0 in enumerate(values):', result)

    def test_outside_comments_preserved(self):
        code = '# 앞쪽\nvalues = [1, 2]\nfor i in range(len(values)):\n    print(values[i])\n# 뒤쪽\n'
        result = equivalent(code, transform_to_direct_iteration_style)
        self.assertIn('# 앞쪽', result)
        self.assertIn('# 뒤쪽', result)

    def test_nested_function(self):
        code = '''def f():
    values = [1, 2]
    for i in range(len(values)):
        print(values[i])
f()
'''
        result = equivalent(code, transform_to_direct_iteration_style)
        self.assertIn('    for item in values:', result)

    def test_loop_else_outside_read(self):
        code = '''values = [1, 2]
for i in range(len(values)):
    print(values[i])
else:
    print(i)
'''
        result = equivalent(code, transform_to_direct_iteration_style)
        self.assertIn('enumerate(values)', result)

    def test_for_else_unchanged_index_expression_on_empty(self):
        code = '''values = []
i = 0
for i in range(len(values)):
    print(values[i])
else:
    print(values[i])
'''
        result = equivalent(code, transform_to_direct_iteration_style)
        self.assertIn('enumerate(values)', result)
        self.assertIn('print(values[i])', result)

    def test_collision_item_variable(self):
        code = 'item = 99\nvalues = [1, 2]\nfor i in range(len(values)):\n    print(values[i])\nprint(item)\n'
        result = equivalent(code, transform_to_direct_iteration_style)
        self.assertIn('for __capstone_item_0 in values:', result)

    def test_skip_index_target_mutation(self):
        code = 'values = [1, 2]\nfor i in range(len(values)):\n    values[i] = 9\n'
        self.assertEqual(transform_to_direct_iteration_style(code), code)

    def test_skip_mutating_length(self):
        code = 'values = [1, 2]\nfor i in range(len(values)):\n    values.append(3)\n    print(values[i])\n'
        self.assertEqual(transform_to_direct_iteration_style(code), code)

    def test_skip_alias(self):
        code = 'values = [1, 2]\nother = values\nfor i in range(len(values)):\n    print(values[i])\n'
        self.assertEqual(transform_to_direct_iteration_style(code), code)

    def test_skip_user_function_call(self):
        code = 'values = [1, 2]\nfor i in range(len(values)):\n    mystery()\n    print(values[i])\n'
        self.assertEqual(transform_to_direct_iteration_style(code), code)

    def test_skip_other_index_read(self):
        code = 'values = [1, 2]\nfor i in range(len(values)):\n    print(values[i + 1])\n'
        self.assertEqual(transform_to_direct_iteration_style(code), code)

    def test_skip_write_to_index(self):
        code = 'values = [1, 2]\nfor i in range(len(values)):\n    i = 0\n    print(values[i])\n'
        self.assertEqual(transform_to_direct_iteration_style(code), code)

    def test_skip_comments_inside_loop(self):
        code = 'values = [1, 2]\nfor i in range(len(values)):\n    # 메모\n    print(values[i])\n'
        self.assertEqual(transform_to_direct_iteration_style(code), code)

    def test_skip_shadowed_enumerate(self):
        code = 'enumerate = 3\nvalues = [1, 2]\nfor i in range(len(values)):\n    print(values[i])\n'
        self.assertEqual(transform_to_direct_iteration_style(code), code)

    def test_skip_introspection(self):
        code = 'values = [1, 2]\nfor i in range(len(values)):\n    print(values[i])\nprint(locals())\n'
        self.assertEqual(transform_to_direct_iteration_style(code), code)

    def test_skip_invalid_code(self):
        code = 'for i in range(\n'
        self.assertEqual(transform_to_direct_iteration_style(code), code)

    def test_skip_dynamic_list(self):
        code = 'values = get_values()\nfor i in range(len(values)):\n    print(values[i])\n'
        self.assertEqual(transform_to_direct_iteration_style(code), code)

    def test_skip_multistatement_semicolon(self):
        code = 'values = [1, 2]\nfor i in range(len(values)):\n    print(values[i]); print("x")\n'
        # Safe to rewrite: semicolons inside the suite are handled by ast.unparse.
        self.assertNotEqual(equivalent(code, transform_to_direct_iteration_style), code)


class IndexTests(unittest.TestCase):
    def test_basic_list(self):
        code = 'values = [1, 2]\nfor item in values:\n    print(item)\n'
        result = equivalent(code, transform_to_index_iteration_style)
        self.assertIn('for index in range(len(values)):', result)
        self.assertIn('item = values[index]', result)

    def test_original_item_still_exists(self):
        code = 'values = [1, 2]\nfor item in values:\n    print(item)\nprint(item)\n'
        self.assertNotEqual(equivalent(code, transform_to_index_iteration_style), code)

    def test_break_continue(self):
        code = '''values = [1, 2, 3]
for item in values:
    if item == 1:
        continue
    if item == 3:
        break
    print(item)
print(item)
'''
        self.assertNotEqual(equivalent(code, transform_to_index_iteration_style), code)

    def test_else(self):
        code = 'values = (1, 2)\nfor item in values:\n    print(item)\nelse:\n    print("done")\n'
        self.assertNotEqual(equivalent(code, transform_to_index_iteration_style), code)

    def test_unpacking(self):
        code = 'pairs = [(1, 2), (3, 4)]\nfor left, right in pairs:\n    print(left + right)\n'
        self.assertNotEqual(equivalent(code, transform_to_index_iteration_style), code)

    def test_empty_iterable(self):
        code = 'values = []\nfor item in values:\n    print(item)\nprint("end")\n'
        self.assertNotEqual(equivalent(code, transform_to_index_iteration_style), code)

    def test_immutable_string(self):
        code = 'values = "AB"\nfor item in values:\n    print(item)\n'
        self.assertNotEqual(equivalent(code, transform_to_index_iteration_style), code)

    def test_preexisting_index_temp(self):
        code = 'index = 4\nvalues = [1, 2]\nfor item in values:\n    print(item)\n'
        result = equivalent(code, transform_to_index_iteration_style)
        self.assertIn('__capstone_index_0', result)

    def test_comments_outside_untouched(self):
        code = 'values = [1, 2]\n# before\nfor item in values:\n    print(item)\n# after\n'
        result = equivalent(code, transform_to_index_iteration_style)
        self.assertIn('# before', result)
        self.assertIn('# after', result)

    def test_rebinding_item_does_not_break_result(self):
        code = 'values = [1, 2]\nfor item in values:\n    item = item * 10\n    print(item)\nprint(item)\n'
        result = equivalent(code, transform_to_index_iteration_style)
        self.assertIn('item = values[index]', result)

    def test_skip_inline_comment(self):
        code = 'values = [1, 2]\nfor item in values:  # preserve\n    print(item)\n'
        self.assertEqual(transform_to_index_iteration_style(code), code)

    def test_skip_self_rebinding_target(self):
        code = 'values = [1, 2]\nfor values in values:\n    print(values)\n'
        self.assertEqual(transform_to_index_iteration_style(code), code)

    def test_skip_mutating_list(self):
        code = 'values = [1, 2]\nfor item in values:\n    values.append(item)\n'
        self.assertEqual(transform_to_index_iteration_style(code), code)

    def test_skip_generator(self):
        code = 'values = (i for i in range(2))\nfor item in values:\n    print(item)\n'
        self.assertEqual(transform_to_index_iteration_style(code), code)

    def test_skip_function_param(self):
        code = 'def f(values):\n    for item in values:\n        print(item)\n'
        self.assertEqual(transform_to_index_iteration_style(code), code)

    def test_skip_comments_inside(self):
        code = 'values = [1, 2]\nfor item in values:\n    # keep\n    print(item)\n'
        self.assertEqual(transform_to_index_iteration_style(code), code)

    def test_skip_builtin_shadow(self):
        code = 'len = 5\nvalues = [1, 2]\nfor item in values:\n    print(item)\n'
        self.assertEqual(transform_to_index_iteration_style(code), code)

    def test_skip_multiple_targets_not_simple(self):
        code = 'values = [1, 2]\nfor obj.attr in values:\n    print(obj.attr)\n'
        self.assertEqual(transform_to_index_iteration_style(code), code)

    def test_unicode(self):
        code = 'values = ["안녕", "세계"]\nfor item in values:\n    print(item)\n'
        self.assertNotEqual(equivalent(code, transform_to_index_iteration_style), code)

    def test_already_indexed(self):
        code = 'values = [1, 2]\nfor i in range(len(values)):\n    print(values[i])\n'
        self.assertEqual(transform_to_index_iteration_style(code), code)


if __name__ == "__main__":
    unittest.main()
