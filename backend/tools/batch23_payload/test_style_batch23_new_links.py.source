"""Batch 23: positive representative triplets, rejection and planning tests.

Only trusted fixture code is executed. These examples are not a proof of
semantics for every program (introspection/tracing in particular).
"""
from __future__ import annotations

import ast
import subprocess
import sys
import unittest

from app.services.improvement.safe_batch23_service import (
    transform_safe_counted_while_to_guard_break as break_transform,
    transform_safe_readonly_global_declaration as global_transform,
)
from app.services.style_tag_transform_map_service import (
    CREATE_ACTION_BY_TAG, COMPARE_ONLY_TAGS, get_create_action_for_tag,
)
from app.services.style_apply_service import _get_transform_function
from app.services.style_transform_plan_service import build_transform_plan


def plan(saved=None, target=None, missing=None):
    return build_transform_plan({
        'missing_syntax_tags': missing or [], 'missing_concept_tags': [],
        'style_syntax_names': set(), 'style_concept_names': set(),
        'target_syntax_names': set(), 'target_concept_names': set(),
        'style_metrics': saved or {},
        'target_analysis': {'metrics': target or {}},
    })


class BreakTagTriplets(unittest.TestCase):
    def test_basic(self):
        src = 'n = 0\nwhile n < 3:\n    print(n)\n    n += 1\n'
        after = break_transform(src)
        self.assertIn('while True:\n    if not (n < 3):\n        break\n', after)
        self.assertIn('    print(n)\n    n += 1\n', after)
        ast.parse(after)

    def test_additional(self):
        src = 'n = 7\nwhile n > 4:\n    n -= 1\n    print(n)\n'
        after = break_transform(src)
        self.assertIn('if not (n > 4):\n        break\n', after)
        ast.parse(after)

    def test_complex(self):
        src = ('first = 1\nwhile first <= 2:\n    print(first)\n    first += 1\n'
               'last = 8\nwhile last != 6:\n    print(last)\n    last -= 1\n')
        after = break_transform(src)
        self.assertEqual(after.count('        break'), 2)
        ast.parse(after)


class GlobalTagTriplets(unittest.TestCase):
    def test_basic(self):
        src = 'x = 5\ndef get():\n    return x\n'
        self.assertEqual(global_transform(src),
                         'x = 5\ndef get():\n    global x\n    return x\n')

    def test_additional(self):
        src = 'greeting = "안녕하세요"\ndef message():\n    return greeting\n'
        after = global_transform(src)
        self.assertIn('    global greeting\n    return greeting\n', after)

    def test_complex(self):
        src = ('x = 1\ny = True\ndef get_x():\n    return x\n'
               'def get_y():\n    return y\nprint(get_x(), get_y())\n')
        after = global_transform(src)
        self.assertIn('    global x\n', after)
        self.assertIn('    global y\n', after)
        ast.parse(after)


class Batch23Safety(unittest.TestCase):
    def test_break_else_rejected(self):
        s = 'x = 0\nwhile x < 3:\n    x += 1\nelse:\n    print("done")\n'
        self.assertEqual(break_transform(s), s)

    def test_break_dynamic_condition_rejected(self):
        s = 'x = 0\nwhile f(x):\n    x += 1\n'
        self.assertEqual(break_transform(s), s)

    def test_break_nested_function_rejected(self):
        s = 'def run():\n    x = 0\n    while x < 3:\n        x += 1\n'
        self.assertEqual(break_transform(s), s)

    def test_break_if_in_body_rejected(self):
        s = 'x = 0\nwhile x < 3:\n    if x == 1:\n        print(x)\n    x += 1\n'
        self.assertEqual(break_transform(s), s)

    def test_break_continue_rejected(self):
        s = 'x = 0\nwhile x < 3:\n    x += 1\n    continue\n'
        self.assertEqual(break_transform(s), s)

    def test_break_no_increment_rejected(self):
        s = 'x = 0\nwhile x < 3:\n    print(x)\n'
        self.assertEqual(break_transform(s), s)

    def test_break_nonliteral_initial_rejected(self):
        s = 'x = f()\nwhile x < 3:\n    x += 1\n'
        self.assertEqual(break_transform(s), s)

    def test_break_comment_in_header_rejected(self):
        s = 'x = 0\nwhile x < 3: # note\n    x += 1\n'
        self.assertEqual(break_transform(s), s)

    def test_break_crlf_preserved(self):
        s = 'x = 0\r\nwhile x < 2:\r\n    x += 1\r\n'
        self.assertEqual(break_transform(s),
                         'x = 0\r\nwhile True:\r\n    if not (x < 2):\r\n'
                         '        break\r\n    x += 1\r\n')

    def test_break_unicode_body_preserved(self):
        s = 'x = 0\nwhile x < 2:\n    print("한글")\n    x += 1\n'
        self.assertIn('print("한글")', break_transform(s))

    def test_break_global_dynamic_rejected(self):
        s = 'x = 0\nwhile x < 2:\n    x += 1\ny = globals()\n'
        self.assertEqual(break_transform(s), s)

    def test_global_arguments_not_modified(self):
        s = 'x = 1\ndef get(x):\n    return x\n'
        self.assertEqual(global_transform(s), s)

    def test_global_assignment_inside_not_modified(self):
        s = 'x = 1\ndef get():\n    x = 3\n    return x\n'
        self.assertEqual(global_transform(s), s)

    def test_global_closure_not_modified(self):
        s = 'def outer():\n    x = 1\n    def inner():\n        return x\n    return inner()\n'
        self.assertEqual(global_transform(s), s)

    def test_global_missing_binding_not_modified(self):
        s = 'def get():\n    return x\n'
        self.assertEqual(global_transform(s), s)

    def test_global_decorator_not_modified(self):
        s = 'x = 1\n@decorator\ndef get():\n    return x\n'
        self.assertEqual(global_transform(s), s)

    def test_global_docstring_not_modified(self):
        s = 'x = 1\ndef get():\n    "doc"\n    return x\n'
        self.assertEqual(global_transform(s), s)

    def test_global_crlf_preserved(self):
        s = 'x = 1\r\ndef get():\r\n    return x\r\n'
        self.assertEqual(global_transform(s),
                         'x = 1\r\ndef get():\r\n    global x\r\n    return x\r\n')

    def test_global_dynamic_rejected(self):
        s = 'x = 1\ndef get():\n    return x\nprint(globals())\n'
        self.assertEqual(global_transform(s), s)

    def test_invalid_python_unmodified(self):
        s = 'def wrong(\n'
        self.assertEqual(global_transform(s), s)
        self.assertEqual(break_transform(s), s)

    def test_execution_equivalence_break(self):
        src = 'i = 0\nwhile i < 3:\n    print(i)\n    i += 1\n'
        dst = break_transform(src)
        self.assertNotEqual(src, dst)
        self._same_exec(src, dst)

    def test_execution_equivalence_global(self):
        src = 'x = 5\ndef get():\n    return x\nprint(get())\n'
        dst = global_transform(src)
        self.assertNotEqual(src, dst)
        self._same_exec(src, dst)

    def _same_exec(self, left, right):
        results = []
        for src in (left, right):
            p = subprocess.run([sys.executable, '-I', '-c', src], capture_output=True,
                               text=True, timeout=3)
            results.append((p.returncode, p.stdout, p.stderr))
        self.assertEqual(*results)

    def test_mapping_and_dispatch(self):
        self.assertEqual(get_create_action_for_tag('break문'), 'create_safe_counted_break')
        self.assertEqual(get_create_action_for_tag('전역 변수 사용'), 'create_safe_readonly_global')
        self.assertIs(_get_transform_function('create_safe_counted_break'), break_transform)
        self.assertIs(_get_transform_function('create_safe_readonly_global'), global_transform)
        self.assertEqual(len(CREATE_ACTION_BY_TAG), 88)
        self.assertEqual(len(COMPARE_ONLY_TAGS), 14)

    def test_metrics_gate(self):
        saved = {'break_count': 2, 'global_count': 1}
        target = {'loop_count': 1, 'function_count': 1,
                  'assign_count': 1, 'break_count': 0, 'global_count': 0}
        actions = [a['action'] for a in plan(saved, target)['actions']]
        self.assertIn('create_safe_counted_break', actions)
        self.assertIn('create_safe_readonly_global', actions)
        self.assertEqual(actions.count('create_safe_counted_break'), 1)
        self.assertEqual(actions.count('create_safe_readonly_global'), 1)

    def test_no_style_preference(self):
        actions = [a['action'] for a in plan({}, {'loop_count': 1,
                  'function_count': 1, 'assign_count': 1})['actions']]
        self.assertNotIn('create_safe_counted_break', actions)
        self.assertNotIn('create_safe_readonly_global', actions)

    def test_target_already_has_preference(self):
        actions = [a['action'] for a in plan({'break_count': 1, 'global_count': 1},
                  {'break_count': 1, 'global_count': 1, 'loop_count': 1,
                   'function_count': 1, 'assign_count': 1})['actions']]
        self.assertNotIn('create_safe_counted_break', actions)
        self.assertNotIn('create_safe_readonly_global', actions)

    def test_missing_label_alone_not_selected(self):
        missing = [{'tag': 'break문'}, {'tag': '전역 변수 사용'}]
        actions = [a['action'] for a in plan({}, {}, missing)['actions']]
        self.assertNotIn('create_safe_counted_break', actions)
        self.assertNotIn('create_safe_readonly_global', actions)


if __name__ == '__main__':
    unittest.main()
