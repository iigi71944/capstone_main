"""Batch 24 conservative import/output style links and safety regression tests."""
from __future__ import annotations

import ast
import subprocess
import sys
import unittest

from app.services.improvement.safe_batch24_service import (
    transform_simple_print_to_explicit_builtins_import as import_transform,
    transform_simple_literal_print_arguments as io_transform,
)
from app.services.style_tag_transform_map_service import (
    CREATE_ACTION_BY_TAG, COMPARE_ONLY_TAGS, get_create_action_for_tag,
)
from app.services.style_apply_service import _get_transform_function
from app.services.style_transform_plan_service import build_transform_plan


def _plan(saved=None, target=None, missing=None):
    return build_transform_plan({
        'missing_syntax_tags': missing or [], 'missing_concept_tags': [],
        'style_syntax_names': set(), 'style_concept_names': set(),
        'target_syntax_names': set(), 'target_concept_names': set(),
        'style_metrics': saved or {},
        'target_analysis': {'metrics': target or {}},
    })


class ImportTagTriplets(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(import_transform("print('hello')\n"),
                         "import builtins\nbuiltins.print('hello')\n")

    def test_additional(self):
        self.assertEqual(import_transform('message = "Hello"\nprint(message)\n'),
                         'import builtins\nmessage = "Hello"\nbuiltins.print(message)\n')

    def test_complex(self):
        source = 'x = 3\r\nprint(x)\r\nprint("끝")\r\n'
        self.assertEqual(import_transform(source),
                         'import builtins\r\nx = 3\r\nbuiltins.print(x)\r\nbuiltins.print("끝")\r\n')


class OutputTagTriplets(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(io_transform('print("a", "b")\n'), "print('a b')\n")

    def test_additional(self):
        self.assertEqual(io_transform("print('a', 'b', 'c')\n"), "print('a b c')\n")

    def test_complex(self):
        before = 'print("안녕", "세상")\nprint("A", "B", "C")  # after\n'
        after = io_transform(before)
        self.assertEqual(after, "print('안녕 세상')\nprint('A B C')  # after\n")


class Batch24Safety(unittest.TestCase):
    def test_print_shadow_assignment(self):
        src = "print = 2\nprint('hi')\n"
        self.assertEqual(import_transform(src), src)
        self.assertEqual(io_transform(src), src)

    def test_dynamic_builtins_assignment(self):
        src = "builtins = 2\nprint('hi')\n"
        self.assertEqual(import_transform(src), src)

    def test_future_import(self):
        src = 'from __future__ import annotations\nprint("hi")\n'
        self.assertEqual(import_transform(src), src)

    def test_import_present(self):
        src = 'import math\nprint("hi")\n'
        self.assertEqual(import_transform(src), src)
        self.assertEqual(io_transform(src), src)

    def test_comments_first(self):
        src = '# encoding: utf-8\nprint("hi")\n'
        self.assertEqual(import_transform(src), src)

    def test_function_and_class(self):
        for src in ('def f():\n    print("hi")\n',
                    'class C:\n    print("hi")\n'):
            self.assertEqual(import_transform(src), src)
            self.assertEqual(io_transform(src), src)

    def test_keyword_print(self):
        src = "print('a','b',sep='-')\n"
        self.assertEqual(import_transform(src), src)
        self.assertEqual(io_transform(src), src)

    def test_multiline_call(self):
        src = "print(\n  'a',\n  'b'\n)\n"
        self.assertEqual(import_transform(src), src)
        self.assertEqual(io_transform(src), src)

    def test_non_string_print(self):
        src = 'print(1, 2)\n'
        self.assertEqual(io_transform(src), src)
        self.assertNotEqual(import_transform(src), src)

    def test_name_args_not_combined(self):
        src = "a = 'a'\nb = 'b'\nprint(a, b)\n"
        self.assertEqual(io_transform(src), src)

    def test_undefined_name_refused(self):
        src = 'print(other)\n'
        self.assertEqual(import_transform(src), src)

    def test_mutating_expression_refused(self):
        src = 'print(f())\n'
        self.assertEqual(import_transform(src), src)
        self.assertEqual(io_transform(src), src)

    def test_loop_refused(self):
        src = 'for _ in [1]:\n    print("hi")\n'
        self.assertEqual(import_transform(src), src)

    def test_invalid_python(self):
        src = 'def broken(\n'
        self.assertEqual(import_transform(src), src)
        self.assertEqual(io_transform(src), src)

    def test_empty_and_non_text(self):
        self.assertEqual(import_transform(''), '')
        self.assertEqual(io_transform(''), '')
        self.assertIsNone(import_transform(None))

    def test_no_print(self):
        src = 'x = 3\n'
        self.assertEqual(import_transform(src), src)

    def test_unicode_and_crlf_output(self):
        src = 'print("서울", "경기")\r\n'
        self.assertEqual(io_transform(src), "print('서울 경기')\r\n")

    def test_both_transformations_same_execution(self):
        before = 'name = "Jin"\nprint("안녕", "세상")\nprint(name)\n'
        after = import_transform(io_transform(before))
        self.assertNotEqual(before, after)
        ast.parse(after)
        outputs = []
        for source in (before, after):
            r = subprocess.run([sys.executable, '-I', '-c', source],
                               capture_output=True, text=True, timeout=3)
            outputs.append((r.returncode, r.stdout, r.stderr))
        self.assertEqual(*outputs)

    def test_mapping_dispatch_and_count(self):
        self.assertEqual(get_create_action_for_tag('import문'), 'create_safe_explicit_builtins_import')
        self.assertEqual(get_create_action_for_tag('입출력 중심 코드'), 'create_safe_literal_print_merge')
        self.assertIs(_get_transform_function('create_safe_explicit_builtins_import'), import_transform)
        self.assertIs(_get_transform_function('create_safe_literal_print_merge'), io_transform)
        # CAPSTONE_BATCH26_LEGACY_MINIMUM_V1: later tags extend the registry.
        self.assertGreaterEqual(len(CREATE_ACTION_BY_TAG), 90)
        self.assertLessEqual(len(COMPARE_ONLY_TAGS), 12)
        self.assertEqual(len(CREATE_ACTION_BY_TAG) + len(COMPARE_ONLY_TAGS), 102)

    def test_style_metric_gates(self):
        saved = {'import_count': 1, 'print_call_count': 1,
                 'positional_arg_count': 1, 'string_literal_count': 2}
        target = {'import_count': 0, 'print_call_count': 1,
                  'positional_arg_count': 2, 'string_literal_count': 2}
        actions = [x['action'] for x in _plan(saved, target)['actions']]
        self.assertIn('create_safe_literal_print_merge', actions)
        self.assertIn('create_safe_explicit_builtins_import', actions)
        self.assertLess(actions.index('create_safe_literal_print_merge'),
                        actions.index('create_safe_explicit_builtins_import'))

    def test_style_without_metric_no_action(self):
        target = {'import_count': 0, 'print_call_count': 1, 'positional_arg_count': 2}
        actions = [x['action'] for x in _plan({}, target)['actions']]
        self.assertNotIn('create_safe_literal_print_merge', actions)
        self.assertNotIn('create_safe_explicit_builtins_import', actions)

    def test_target_already_contains_import(self):
        saved = {'import_count': 1, 'print_call_count': 1,
                 'positional_arg_count': 1, 'string_literal_count': 2}
        target = {'import_count': 1, 'print_call_count': 1,
                  'positional_arg_count': 2, 'string_literal_count': 2}
        actions = [x['action'] for x in _plan(saved, target)['actions']]
        self.assertNotIn('create_safe_explicit_builtins_import', actions)

    def test_missing_tag_alone_no_automatic_change(self):
        diff = _plan({}, {'print_call_count': 1}, [{'tag': 'import문'}, {'tag': '입출력 중심 코드'}])
        acts = [x['action'] for x in diff['actions']]
        self.assertNotIn('create_safe_explicit_builtins_import', acts)
        self.assertNotIn('create_safe_literal_print_merge', acts)

    def test_unsafe_tags_remain_compare_only(self):
        # CAPSTONE_BATCH27_LEGACY_STATUS_V1: file I/O is now narrowly linked.
        # Batch31: formerly risky tags now have guarded closed-module transforms.
        for tag in ('await 사용', '기본 매개변수'):
            self.assertIn(tag, CREATE_ACTION_BY_TAG)
            self.assertNotIn(tag, COMPARE_ONLY_TAGS)


if __name__ == '__main__':
    unittest.main()
