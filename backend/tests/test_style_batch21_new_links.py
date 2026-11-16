"""Batch 21: positive tag fixtures, conservative rejection and wiring tests.

Only trusted test code is executed; user-submitted code is not run here.
"""
from __future__ import annotations
import ast
import subprocess
import sys
import unittest

from app.services.improvement.safe_batch21_service import (
    transform_safe_builtin_input, transform_debug_guard_to_assert,
)
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import (
    CREATE_ACTION_BY_TAG, COMPARE_ONLY_TAGS, get_create_action_for_tag,
)
from app.services.style_transform_plan_service import build_transform_plan


def plan(saved=None, target=None, missing=None):
    return build_transform_plan({
        'missing_syntax_tags': missing or [], 'missing_concept_tags': [],
        'style_syntax_names': set(), 'style_concept_names': set(),
        'target_syntax_names': set(), 'target_concept_names': set(),
        'style_metrics': saved or {},
        'target_analysis': {'metrics': target or {}},
    })


class InputTagTriplets(unittest.TestCase):
    def test_basic(self):
        s = 'import builtins\nanswer = builtins.input("value: ")\n'
        self.assertEqual(transform_safe_builtin_input(s),
                         'import builtins\nanswer = input("value: ")\n')

    def test_additional(self):
        s = 'import builtins\nanswer = builtins.input("한글: ")  # keep\n'
        self.assertEqual(transform_safe_builtin_input(s),
                         'import builtins\nanswer = input("한글: ")  # keep\n')

    def test_complex(self):
        s = ('import builtins\na = builtins.input("first: ")\n'
             'b = builtins.input("second: ")\nprint(a, b)\n')
        expected = s.replace('builtins.input', 'input')
        self.assertEqual(transform_safe_builtin_input(s), expected)


class AssertTagTriplets(unittest.TestCase):
    def test_basic(self):
        s = 'flag = True\nif __debug__:\n    if not flag:\n        raise AssertionError\n'
        self.assertEqual(transform_debug_guard_to_assert(s), 'flag = True\nassert flag\n')

    def test_additional(self):
        s = "ok = True\nif __debug__:\n    if not ok:\n        raise AssertionError('bad')\n"
        self.assertEqual(transform_debug_guard_to_assert(s), "ok = True\nassert ok, 'bad'\n")

    def test_complex(self):
        s = ('def check(value):\n    if __debug__:\n'
             '        if not value:\n            raise AssertionError("invalid")\n'
             '    return 42\n')
        expected = ('def check(value):\n    assert value, "invalid"\n    return 42\n')
        self.assertEqual(transform_debug_guard_to_assert(s), expected)


class Batch21Safety(unittest.TestCase):
    def test_input_no_import(self):
        s = 'name = builtins.input()\n'
        self.assertEqual(transform_safe_builtin_input(s), s)

    def test_input_import_after(self):
        s = 'name = builtins.input()\nimport builtins\n'
        self.assertEqual(transform_safe_builtin_input(s), s)

    def test_input_shadowed_name(self):
        s = 'import builtins\ninput = lambda x: x\na = builtins.input()\n'
        self.assertEqual(transform_safe_builtin_input(s), s)

    def test_input_dynamic_namespace(self):
        s = 'import builtins\nglobals()["input"] = x\na = builtins.input()\n'
        self.assertEqual(transform_safe_builtin_input(s), s)

    def test_input_builtin_attribute_overwritten(self):
        s = 'import builtins\nbuiltins.input = other\na = builtins.input()\n'
        self.assertEqual(transform_safe_builtin_input(s), s)

    def test_input_nested_function_untouched(self):
        s = 'import builtins\ndef f():\n    return builtins.input()\n'
        self.assertEqual(transform_safe_builtin_input(s), s)

    def test_input_from_star_untouched(self):
        s = 'import builtins\nfrom other import *\na = builtins.input()\n'
        self.assertEqual(transform_safe_builtin_input(s), s)

    def test_input_duplicate_import_untouched(self):
        s = 'import builtins\nimport builtins\na = builtins.input()\n'
        self.assertEqual(transform_safe_builtin_input(s), s)

    def test_input_aliased_import_untouched(self):
        s = 'import builtins as b\na = b.input()\n'
        self.assertEqual(transform_safe_builtin_input(s), s)

    def test_input_lineno_comment_preserved(self):
        s = 'import builtins\n# comment\na: str = builtins.input()\n'
        self.assertEqual(transform_safe_builtin_input(s),
                         'import builtins\n# comment\na: str = input()\n')

    def test_input_crlf_preserved(self):
        s = 'import builtins\r\na = builtins.input("value")\r\n'
        self.assertEqual(transform_safe_builtin_input(s),
                         'import builtins\r\na = input("value")\r\n')

    def test_assert_no_debug_guard(self):
        s = 'if not ready:\n    raise AssertionError("bad")\n'
        self.assertEqual(transform_debug_guard_to_assert(s), s)

    def test_assert_not_plain_raise(self):
        s = 'if __debug__:\n    raise AssertionError("bad")\n'
        self.assertEqual(transform_debug_guard_to_assert(s), s)

    def test_assert_no_else_allowed(self):
        s = 'if __debug__:\n    if not ready:\n        raise AssertionError\n    else:\n        pass\n'
        self.assertEqual(transform_debug_guard_to_assert(s), s)

    def test_assert_extra_stmt_not_allowed(self):
        s = 'if __debug__:\n    if not ready:\n        raise AssertionError\n    print("x")\n'
        self.assertEqual(transform_debug_guard_to_assert(s), s)

    def test_assert_shadowed_AssertionError(self):
        s = 'AssertionError = ValueError\nif __debug__:\n    if not ok:\n        raise AssertionError\n'
        self.assertEqual(transform_debug_guard_to_assert(s), s)

    def test_assert_dynamic_err_message(self):
        s = 'if __debug__:\n    if not ok:\n        raise AssertionError(get_message())\n'
        self.assertEqual(transform_debug_guard_to_assert(s), s)

    def test_assert_comment_inside_block(self):
        s = 'if __debug__:\n    # note\n    if not ok:\n        raise AssertionError\n'
        self.assertEqual(transform_debug_guard_to_assert(s), s)

    def test_assert_crlf_preserved(self):
        s = 'if __debug__:\r\n    if not ok:\r\n        raise AssertionError\r\n'
        self.assertEqual(transform_debug_guard_to_assert(s), 'assert ok\r\n')

    def test_invalid_python_returns_original(self):
        s = 'def broken(\n'
        self.assertEqual(transform_safe_builtin_input(s), s)
        self.assertEqual(transform_debug_guard_to_assert(s), s)

    def test_optimizer_semantics(self):
        original = ('flag = False\nif __debug__:\n    if not flag:\n'
                    '        raise AssertionError("invalid")\nprint("done")\n')
        after = transform_debug_guard_to_assert(original)
        self.assertNotEqual(after, original)
        for switches in ([], ['-O']):
            a = subprocess.run([sys.executable, *switches, '-I', '-c', original],
                               capture_output=True, text=True, timeout=3)
            b = subprocess.run([sys.executable, *switches, '-I', '-c', after],
                               capture_output=True, text=True, timeout=3)
            self.assertEqual((a.returncode, a.stdout), (b.returncode, b.stdout))
            self.assertIn('AssertionError: invalid', a.stderr) if not switches else self.assertEqual(a.stderr, '')
            self.assertIn('AssertionError: invalid', b.stderr) if not switches else self.assertEqual(b.stderr, '')

    def test_registry_and_dispatch(self):
        self.assertEqual(get_create_action_for_tag('input 사용'), 'create_safe_builtin_input')
        self.assertEqual(get_create_action_for_tag('assert문'), 'create_safe_debug_assert')
        self.assertIs(_get_transform_function('create_safe_builtin_input'), transform_safe_builtin_input)
        self.assertIs(_get_transform_function('create_safe_debug_assert'), transform_debug_guard_to_assert)
        # CAPSTONE_BATCH22_LEGACY_REGISTRY_V1: keep old expectations valid after extensions.
        self.assertGreaterEqual(len(CREATE_ACTION_BY_TAG), 84)
        self.assertLessEqual(len(COMPARE_ONLY_TAGS), 18)
        self.assertEqual(len(CREATE_ACTION_BY_TAG) + len(COMPARE_ONLY_TAGS), 102)

    def test_plan_gates(self):
        saved = {'input_call_count': 2, 'assert_count': 1}
        target = {'attribute_count': 1, 'import_count': 1, 'call_count': 1,
                  'if_count': 1, 'raise_count': 1}
        acts = [a['action'] for a in plan(saved, target)['actions']]
        self.assertIn('create_safe_builtin_input', acts)
        self.assertIn('create_safe_debug_assert', acts)
        self.assertEqual(acts.count('create_safe_builtin_input'), 1)
        self.assertEqual(acts.count('create_safe_debug_assert'), 1)
        self.assertNotIn('create_safe_builtin_input',
                         [a['action'] for a in plan({}, target)['actions']])
        self.assertNotIn('create_safe_debug_assert',
                         [a['action'] for a in plan({}, target)['actions']])
        self.assertNotIn('create_safe_builtin_input',
                         [a['action'] for a in plan(saved, {'input_call_count': 1})['actions']])
        self.assertNotIn('create_safe_debug_assert',
                         [a['action'] for a in plan(saved, {'assert_count': 1})['actions']])

    def test_missing_tags_without_metrics_not_selected(self):
        missing = [{'tag': 'input 사용'}, {'tag': 'assert문'}]
        acts = {a['action'] for a in plan({}, {}, missing)['actions']}
        self.assertFalse(acts & {'create_safe_builtin_input', 'create_safe_debug_assert'})

    def test_real_safe_input_execution(self):
        before = 'import builtins\nname = builtins.input("? ")\nprint("hello", name)\n'
        after = transform_safe_builtin_input(before)
        self.assertNotEqual(before, after)
        for source in (before, after):
            p = subprocess.run([sys.executable, '-I', '-c', source], input='Sam\n',
                               capture_output=True, text=True, timeout=3)
            self.assertEqual(p.returncode, 0)
            self.assertEqual(p.stdout, '? hello Sam\n')


if __name__ == '__main__':
    unittest.main()
