"""Batch27: three real positive shapes per newly linked tag + negative fixtures."""
from __future__ import annotations

import ast
import builtins
import io
import subprocess
import sys
import unittest

from app.services.improvement.safe_batch27_service import (
    transform_safe_module_io_open as open_transform,
    transform_safe_file_io_with as file_transform,
    transform_literal_private_main_to_procedure as procedural_transform,
)
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import (
    CREATE_ACTION_BY_TAG, COMPARE_ONLY_TAGS, get_create_action_for_tag,
)
from app.services.style_transform_plan_service import build_transform_plan


def plan(saved=None, target=None, syntax=(), concepts=(), missing=None):
    return build_transform_plan({
        'missing_syntax_tags': missing or [], 'missing_concept_tags': [],
        'style_syntax_names': set(syntax), 'style_concept_names': set(concepts),
        'target_syntax_names': set(), 'target_concept_names': set(),
        'style_metrics': saved or {},
        'target_analysis': {'metrics': target or {}},
    })


class OpenTagTriplets(unittest.TestCase):
    def test_basic(self):
        before = 'import io\nreader = io.open("notes.txt", "r")\n'
        self.assertEqual(open_transform(before), 'import io\nreader = open("notes.txt", "r")\n')

    def test_additional(self):
        before = "import io\nreader = io.open('x.txt', encoding='utf-8')\n"
        self.assertEqual(open_transform(before), "import io\nreader = open('x.txt', encoding='utf-8')\n")

    def test_complex(self):
        before = 'import io\nreader = io.open("archive.bin", "rb")\n'
        self.assertEqual(open_transform(before), 'import io\nreader = open("archive.bin", "rb")\n')


class FileStructureTriplets(unittest.TestCase):
    def test_basic(self):
        before = ('import io\nwith io.open("notes.txt", "r") as f:\n'
                  '    text = f.read()\n')
        self.assertEqual(file_transform(before),
                         'import io\nwith open("notes.txt", "r") as f:\n    text = f.read()\n')

    def test_additional(self):
        before = ('import io\nwith io.open("notes.txt", encoding="utf-8") as f:\n'
                  '    line = f.readline()\n')
        self.assertEqual(file_transform(before),
                         'import io\nwith open("notes.txt", encoding="utf-8") as f:\n    line = f.readline()\n')

    def test_complex(self):
        before = ('import io\nwith io.open("data.bin", mode="rb") as stream:\n'
                  '    payload = stream.read()\n')
        self.assertEqual(file_transform(before),
                         'import io\nwith open("data.bin", mode="rb") as stream:\n    payload = stream.read()\n')


class ProceduralTagTriplets(unittest.TestCase):
    def test_basic(self):
        before = 'def _main():\n    print("ok")\n_main()\n'
        self.assertEqual(procedural_transform(before), 'print("ok")\n')

    def test_additional(self):
        before = "def _run():\n    print('hi', 'world')\n_run()\n"
        self.assertEqual(procedural_transform(before), "print('hi', 'world')\n")

    def test_complex(self):
        before = 'def _start():\n    print("hello")\n    print("bye")\n_start()\n'
        self.assertEqual(procedural_transform(before), 'print("hello")\nprint("bye")\n')


class Batch27Safety(unittest.TestCase):
    def test_read_only_file_identity(self):
        self.assertIs(io.open, builtins.open)

    def test_bad_module_name(self):
        x = 'import os\nf = io.open("x", "r")\n'
        self.assertEqual(open_transform(x), x)

    def test_no_import(self):
        x = 'f = io.open("x", "r")\n'
        self.assertEqual(open_transform(x), x)

    def test_rebinding_of_open(self):
        x = 'import io\nopen = io.open("x", "r")\n'
        self.assertEqual(open_transform(x), x)

    def test_rebinding_of_io(self):
        x = 'import io\nio = io.open("x", "r")\n'
        self.assertEqual(open_transform(x), x)

    def test_dynamic_filename(self):
        x = 'import io\nf = io.open(get_path(), "r")\n'
        self.assertEqual(open_transform(x), x)

    def test_file_write_is_not_enabled(self):
        x = 'import io\nwith io.open("file.txt", "w") as f:\n    f.write("hello")\n'
        self.assertEqual(file_transform(x), x)

    def test_append_is_not_enabled(self):
        x = 'import io\nf = io.open("file.txt", "a")\n'
        self.assertEqual(open_transform(x), x)

    def test_duplicate_mode_rejected(self):
        x = 'import io\nf = io.open("file.txt", "r", mode="r")\n'
        self.assertEqual(open_transform(x), x)

    def test_extra_module_statements(self):
        x = 'import io\nx = 3\nf = io.open("file.txt", "r")\n'
        self.assertEqual(open_transform(x), x)

    def test_no_file_io_function_scopes(self):
        x = 'import io\ndef f():\n    return io.open("x", "r")\n'
        self.assertEqual(file_transform(x), x)

    def test_different_import_alias(self):
        x = 'import io as alt\nf = alt.open("x", "r")\n'
        self.assertEqual(open_transform(x), x)

    def test_risky_name_mutation(self):
        x = 'import io\nwith io.open("x", "r") as open:\n    pass\n'
        self.assertEqual(file_transform(x), x)

    def test_procedure_public_main(self):
        x = 'def main():\n    print("ok")\nmain()\n'
        self.assertEqual(procedural_transform(x), x)

    def test_procedure_function_has_params(self):
        x = 'def _main(x):\n    print("ok")\n_main(3)\n'
        self.assertEqual(procedural_transform(x), x)

    def test_procedure_called_twice(self):
        x = 'def _main():\n    print("ok")\n_main()\n_main()\n'
        self.assertEqual(procedural_transform(x), x)

    def test_procedure_uses_variable(self):
        x = 'def _main():\n    print(message)\n_main()\n'
        self.assertEqual(procedural_transform(x), x)

    def test_procedure_with_comment(self):
        x = 'def _main():\n    # say hi\n    print("hello")\n_main()\n'
        self.assertEqual(procedural_transform(x), x)

    def test_procedure_with_dynamic_import(self):
        x = 'import os\ndef _main():\n    print("x")\n_main()\n'
        self.assertEqual(procedural_transform(x), x)

    def test_procedure_output_equivalent(self):
        src = 'def _main():\n    print("hello")\n    print("world")\n_main()\n'
        out = procedural_transform(src)
        self.assertNotEqual(src, out)
        results = []
        for text in (src, out):
            p = subprocess.run([sys.executable, '-I', '-c', text],
                               capture_output=True, text=True, timeout=3)
            results.append((p.returncode, p.stdout, p.stderr))
        self.assertEqual(*results)

    def test_crlf_and_unicode(self):
        src = 'import io\r\nf = io.open("서울.txt", "r")\r\n'
        self.assertEqual(open_transform(src), 'import io\r\nf = open("서울.txt", "r")\r\n')
        psrc = 'def _main():\r\n    print("서울")\r\n_main()\r\n'
        self.assertEqual(procedural_transform(psrc), 'print("서울")\r\n')

    def test_invalid_code(self):
        x = 'import io\nf = io.open(\n'
        self.assertEqual(open_transform(x), x)
        self.assertEqual(file_transform(x), x)
        self.assertEqual(procedural_transform(x), x)

    def test_registry_count_and_dispatch(self):
        mapping = {
            'open 사용': ('create_safe_module_io_open', open_transform),
            '파일 입출력 구조': ('create_safe_file_io_with', file_transform),
            '절차형 코드 스타일': ('create_safe_literal_procedural', procedural_transform),
        }
        for tag, (action, transformer) in mapping.items():
            self.assertEqual(get_create_action_for_tag(tag), action)
            self.assertIs(_get_transform_function(action), transformer)
        self.assertEqual(len(CREATE_ACTION_BY_TAG), 95)
        self.assertEqual(len(COMPARE_ONLY_TAGS), 7)

    def test_plan_gates(self):
        saved = {'open_call_count': 1, 'function_count': 0, 'class_count': 0}
        target = {'open_call_count': 0, 'import_count': 1, 'attribute_count': 1,
                  'call_count': 2, 'function_count': 1, 'class_count': 0}
        data = plan(saved, target, syntax={'open 사용'},
                    concepts={'파일 입출력 구조', '절차형 코드 스타일'})
        acts = [item['action'] for item in data['actions']]
        for action in ('create_safe_module_io_open', 'create_safe_file_io_with',
                       'create_safe_literal_procedural'):
            self.assertEqual(acts.count(action), 1)

    def test_plan_no_unobserved_style(self):
        data = plan({}, {'open_call_count': 0, 'import_count': 1, 'attribute_count': 1,
                         'call_count': 2, 'function_count': 1},
                    syntax={'open 사용'}, concepts={'파일 입출력 구조'})
        self.assertNotIn('create_safe_module_io_open', [x['action'] for x in data['actions']])
        self.assertNotIn('create_safe_file_io_with', [x['action'] for x in data['actions']])

    def test_missing_tag_alone(self):
        data = plan({}, {'open_call_count': 0, 'import_count': 1, 'attribute_count': 1},
                    missing=[{'tag':'open 사용'}, {'tag':'절차형 코드 스타일'}])
        acts = [x['action'] for x in data['actions']]
        self.assertNotIn('create_safe_module_io_open', acts)
        self.assertNotIn('create_safe_literal_procedural', acts)


if __name__ == '__main__':
    unittest.main()
