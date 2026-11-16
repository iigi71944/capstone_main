"""Batch 22 positive triplets, side-effect rejection, dispatcher and planner."""
from __future__ import annotations

import ast
import subprocess
import sys
import unittest

from app.services.improvement.safe_batch22_service import (
    transform_literal_unpack_to_assignments as unpack,
    transform_debug_assert_to_raise as explicit_raise,
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


class AssignmentTagTriplets(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(unpack('a, b = (1, 2)\n'), 'a = 1\nb = 2\n')

    def test_additional(self):
        self.assertEqual(unpack('first, second = ("한글", True)  # keep\n'),
                         'first = "한글"\nsecond = True  # keep\n')

    def test_complex(self):
        source = 'left, mid, right = (None, 3.5, "ok")\nprint(left, mid, right)\n'
        result = unpack(source)
        self.assertIn('left = None\nmid = 3.5\nright = "ok"\n', result)
        self.assertNotEqual(source, result)
        ast.parse(result)


class RaiseTagTriplets(unittest.TestCase):
    def test_basic(self):
        source = 'if __debug__:\n    assert flag\n'
        self.assertEqual(explicit_raise(source),
                         'if __debug__:\n    if not flag:\n        raise AssertionError\n')

    def test_additional(self):
        source = "if __debug__:\n    assert ok, 'bad'\n"
        self.assertEqual(explicit_raise(source),
                         "if __debug__:\n    if not ok:\n        raise AssertionError('bad')\n")

    def test_complex(self):
        source = ('def check(flag):\n    if __debug__:\n'
                  '        assert flag, "한글 오류"\n    return 7\n')
        result = explicit_raise(source)
        self.assertIn('        if not flag:\n            raise AssertionError("한글 오류")\n', result)
        self.assertIn('    return 7\n', result)
        ast.parse(result)


class Batch22SafetyTests(unittest.TestCase):
    def test_unpack_function_call_not_rewritten(self):
        source = 'a, b = (f(), 2)\n'
        self.assertEqual(unpack(source), source)

    def test_unpack_name_operand_not_rewritten(self):
        source = 'a, b = (x, 2)\n'
        self.assertEqual(unpack(source), source)

    def test_unpack_duplicate_name_rejected(self):
        source = 'a, a = (1, 2)\n'
        self.assertEqual(unpack(source), source)

    def test_unpack_nested_function_rejected(self):
        source = 'def f():\n    a, b = (1, 2)\n    return a + b\n'
        self.assertEqual(unpack(source), source)

    def test_unpack_multiline_comment_rejected(self):
        source = 'a, b = (1,  # important\n        2)\n'
        self.assertEqual(unpack(source), source)

    def test_unpack_semicolon_rejected(self):
        source = 'a, b = (1, 2); print(a, b)\n'
        self.assertEqual(unpack(source), source)

    def test_unpack_attr_target_rejected(self):
        source = 'obj.a, b = (1, 2)\n'
        self.assertEqual(unpack(source), source)

    def test_unpack_nested_list_rhs_rejected(self):
        source = 'a, b = [1, 2]\n'
        self.assertEqual(unpack(source), source)

    def test_unpack_chain_rejected(self):
        source = 'a = b, c = (1, 2)\n'
        self.assertEqual(unpack(source), source)

    def test_unpack_crlf(self):
        self.assertEqual(unpack('a, b = (1, 2)\r\n'), 'a = 1\r\nb = 2\r\n')

    def test_raise_unprotected_assert_rejected(self):
        source = 'assert flag, "error"\n'
        self.assertEqual(explicit_raise(source), source)

    def test_raise_dynamic_message_rejected(self):
        source = 'if __debug__:\n    assert flag, get_message()\n'
        self.assertEqual(explicit_raise(source), source)

    def test_raise_nonname_condition_rejected(self):
        source = 'if __debug__:\n    assert check(), "bad"\n'
        self.assertEqual(explicit_raise(source), source)

    def test_raise_else_rejected(self):
        source = 'if __debug__:\n    assert flag\nelse:\n    print("disabled")\n'
        self.assertEqual(explicit_raise(source), source)

    def test_raise_extra_stmt_rejected(self):
        source = 'if __debug__:\n    assert flag\n    print("yes")\n'
        self.assertEqual(explicit_raise(source), source)

    def test_raise_shadowed_exception_rejected(self):
        source = 'AssertionError = RuntimeError\nif __debug__:\n    assert flag\n'
        self.assertEqual(explicit_raise(source), source)

    def test_raise_dynamic_namespace_rejected(self):
        source = 'globals()["AssertionError"] = OSError\nif __debug__:\n    assert flag\n'
        self.assertEqual(explicit_raise(source), source)

    def test_raise_comments_rejected(self):
        source = 'if __debug__:\n    # important\n    assert flag\n'
        self.assertEqual(explicit_raise(source), source)

    def test_raise_crlf(self):
        source = 'if __debug__:\r\n    assert flag, "bad"\r\n'
        self.assertEqual(explicit_raise(source),
                         'if __debug__:\r\n    if not flag:\r\n        raise AssertionError("bad")\r\n')

    def test_invalid_python_stays_original(self):
        source = 'def broken(\n'
        self.assertEqual(unpack(source), source)
        self.assertEqual(explicit_raise(source), source)

    def test_unpack_same_behavior(self):
        src = 'a, b = (3, "two")\nprint(a, b)\n'
        dst = unpack(src)
        for code in (src, dst):
            run = subprocess.run([sys.executable, '-I', '-c', code],
                                 capture_output=True, text=True, timeout=3)
            self.assertEqual(run.returncode, 0)
            self.assertEqual(run.stdout, '3 two\n')

    def test_raise_same_behavior_normal_and_optimized(self):
        src = ('def validate(flag):\n    if __debug__:\n'
               '        assert flag, "invalid"\n    return 1\n'
               'try:\n    print(validate(False))\n'
               'except AssertionError as exc:\n    print(type(exc).__name__, str(exc))\n')
        dst = explicit_raise(src)
        self.assertNotEqual(src, dst)
        for option in ([], ['-O']):
            before = subprocess.run([sys.executable, *option, '-I', '-c', src],
                                    capture_output=True, text=True, timeout=3)
            after = subprocess.run([sys.executable, *option, '-I', '-c', dst],
                                   capture_output=True, text=True, timeout=3)
            self.assertEqual((before.returncode, before.stdout, before.stderr),
                             (after.returncode, after.stdout, after.stderr))

    def test_registry_and_dispatch(self):
        self.assertEqual(get_create_action_for_tag('변수 할당'), 'create_safe_literal_unpack_assignments')
        self.assertEqual(get_create_action_for_tag('raise문'), 'create_safe_debug_raise')
        self.assertIs(_get_transform_function('create_safe_literal_unpack_assignments'), unpack)
        self.assertIs(_get_transform_function('create_safe_debug_raise'), explicit_raise)
        self.assertEqual(len(CREATE_ACTION_BY_TAG), 86)
        self.assertEqual(len(COMPARE_ONLY_TAGS), 16)

    def test_plan_gates(self):
        saved = {'assign_count': 5, 'raise_count': 1}
        target = {'assign_count': 1, 'tuple_literal_count': 1,
                  'assert_count': 1, 'if_count': 1}
        actions = [a['action'] for a in plan(saved, target)['actions']]
        self.assertIn('create_safe_literal_unpack_assignments', actions)
        self.assertIn('create_safe_debug_raise', actions)
        self.assertEqual(actions.count('create_safe_literal_unpack_assignments'), 1)
        self.assertEqual(actions.count('create_safe_debug_raise'), 1)
        self.assertNotIn('create_safe_debug_raise',
                         [x['action'] for x in plan({}, target)['actions']])
        self.assertNotIn('create_safe_literal_unpack_assignments',
                         [x['action'] for x in plan(saved, {'assign_count': 5})['actions']])

    def test_missing_tags_alone_never_changes_code(self):
        missing = [{'tag': '변수 할당'}, {'tag': 'raise문'}]
        self.assertFalse({x['action'] for x in plan({}, {}, missing)['actions']} & {
            'create_safe_literal_unpack_assignments', 'create_safe_debug_raise'})

    def test_mutually_conflicting_assert_raise_actions_removed(self):
        saved = {'raise_count': 1, 'assert_count': 1}
        target = {'assert_count': 1, 'if_count': 1, 'raise_count': 1}
        # Here target assert is already present so asserting action is gated out;
        # force a synthetic contradictory set via the family resolver itself.
        from app.services.style_transform_plan_service import _resolve_new_family_actions
        both = [
            {'tag': 'assert문', 'action': 'create_safe_debug_assert'},
            {'tag': 'raise문', 'action': 'create_safe_debug_raise'},
        ]
        self.assertEqual(_resolve_new_family_actions(both), [])


if __name__ == '__main__':
    unittest.main()
