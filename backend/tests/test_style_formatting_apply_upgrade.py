"""Regression coverage for actual formatting application using v1 saved profiles."""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

try:
    import pydantic  # noqa: F401; required only for API-schema integration cases
except ImportError:
    HAS_PYDANTIC = False
else:
    HAS_PYDANTIC = True


from app.services.style_format_apply_service import (
    apply_saved_formatting_style,
    _indent_lines,
    _semicolon_lines,
    _remove_excess_blank_lines,
)
from app.services.style_format_profile_service import extract_formatting_style

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ROOT / 'tools/install_formatting_apply.py'


def profile(code):
    return extract_formatting_style(code)


TWO_SPACE = profile('def calculate(xs):\n  count = 0\n  for x in xs:\n    count += x\n  return count\n')
FOUR_SPACE = profile('def calculate(xs):\n    count = 0\n    for x in xs:\n        count += x\n    return count\n')
SPLIT_STYLE = profile('def f():\n    a = 1\n    b = 2\n    return a + b\n')
SEMI_STYLE = profile('def f():\n    a = 1; b = 2\n    return a + b\n')


def plain_ast(code):
    return ast.dump(ast.parse(code), include_attributes=False)


class FormattingApplyTests(unittest.TestCase):
    def apply(self, code, fmt):
        new, rules, warnings = apply_saved_formatting_style(code, fmt)
        self.assertEqual(plain_ast(code), plain_ast(new))
        return new, rules, warnings

    def test_2_to_4_spaces(self):
        source = 'def f():\n  x = 1\n  if x:\n    return x\n'
        new, rules, _ = self.apply(source, FOUR_SPACE)
        self.assertIn('\n    x = 1\n', new)
        self.assertIn('\n        return x\n', new)
        self.assertTrue(any('들여쓰기' in r for r in rules))

    def test_4_to_2_spaces(self):
        source = 'def f():\n    x = 1\n    if x:\n        return x\n'
        new, _, _ = self.apply(source, TWO_SPACE)
        self.assertIn('\n  x = 1\n', new)
        self.assertIn('\n    return x\n', new)

    def test_deeply_nested_levels(self):
        code = ('def f():\n'
                '    for x in range(2):\n'
                '        if x:\n'
                '            try:\n'
                '                return x\n'
                '            except ValueError:\n'
                '                pass\n')
        new, _, _ = self.apply(code, TWO_SPACE)
        self.assertIn('        return x', new)

    def test_mixed_original_indent_to_spaces(self):
        code = 'def f():\n\tx = 1\n\tif x:\n\t\treturn x\n'
        new, _, _ = self.apply(code, TWO_SPACE)
        self.assertIn('\n  x = 1\n', new)
        self.assertIn('\n    return x\n', new)

    def test_save_tabs_applied(self):
        fmt = profile('def f():\n\tx = 3\n\tif x:\n\t\treturn x\n')
        code = 'def f():\n    x = 3\n    if x:\n        return x\n'
        new, rules, _ = self.apply(code, fmt)
        self.assertIn('\n\tx = 3\n', new)
        self.assertIn('\n\t\treturn x\n', new)
        self.assertTrue(rules)

    def test_comments_inside_function_keep_text(self):
        code = 'def f():\n    # 내부 설명\n    x = 1  # 끝\n    return x\n'
        new, _, _ = self.apply(code, TWO_SPACE)
        self.assertIn('  # 내부 설명', new)
        self.assertIn('x = 1  # 끝', new)

    def test_top_level_comment_preserved(self):
        code = '# comment\ndef f():\n    return 1\n'
        new, _, _ = self.apply(code, TWO_SPACE)
        self.assertTrue(new.startswith('# comment\n'))

    def test_multiline_string_constant_preserved(self):
        code = 'def f():\n    value = """hello\n    keep four spaces\n  keep two\n    """\n    return value\n'
        new, _, _ = self.apply(code, TWO_SPACE)
        self.assertIn('    keep four spaces\n  keep two\n    """', new)

    def test_multiline_docstring_preserved(self):
        code = 'def f():\n    """line 1\n        line 2\n    """\n    return 2\n'
        new, _, _ = self.apply(code, TWO_SPACE)
        self.assertIn('        line 2', new)
        self.assertIn('\n  return 2', new)

    def test_hash_inside_string_preserved(self):
        code = 'def f():\n    return "# not a comment"\n'
        new, _, _ = self.apply(code, TWO_SPACE)
        self.assertIn('"# not a comment"', new)

    def test_inline_semicolon_separated(self):
        code = 'def f():\n    a = 1; b = 2\n    return a + b\n'
        new, rules, _ = self.apply(code, SPLIT_STYLE)
        self.assertIn('    a = 1\n    b = 2', new)
        self.assertTrue(any('줄바꿈' in r for r in rules))

    def test_multiple_semicolons_separated(self):
        code = 'a = 1; b = 2; c = 3\nprint(a + b + c)\n'
        new, _, _ = self.apply(code, SPLIT_STYLE)
        self.assertIn('a = 1\nb = 2\nc = 3', new)

    def test_semicolon_in_string_not_split(self):
        code = 'label = "a;b"\nprint(label)\n'
        new, _, _ = self.apply(code, SPLIT_STYLE)
        self.assertIn('"a;b"', new)

    def test_semicolon_in_comment_not_split(self):
        code = 'x = 1  # a; b\n'
        new, _, _ = self.apply(code, SPLIT_STYLE)
        self.assertIn('# a; b', new)

    def test_inline_compound_body_skip_semicolon(self):
        code = 'if True: a = 1; b = 2\n'
        new, _, _ = self.apply(code, SPLIT_STYLE)
        self.assertEqual(new, code)

    def test_semicolon_inside_parenthesized_call_not_split(self):
        code = 'text = ("a;b")\n'
        new, _, _ = self.apply(code, SPLIT_STYLE)
        self.assertEqual(new, code)

    def test_semicolon_in_double_quoted_string(self):
        code = 'print("one; two")\n'
        new, _, _ = self.apply(code, SPLIT_STYLE)
        self.assertEqual(new, code)

    def test_semicolon_before_hash_comment(self):
        code = 'x=1; y=2  # this is a comment\n'
        new, _, _ = self.apply(code, SPLIT_STYLE)
        self.assertIn('x=1\ny=2  # this is a comment', new)

    def test_trailing_semicolon_kept(self):
        code = 'x = 1;\n'
        new, _, _ = self.apply(code, SPLIT_STYLE)
        self.assertEqual(new, code)

    def test_semi_pref_joins_simple_assignments(self):
        code = 'def f():\n    x = 1\n    y = 2\n    return x + y\n'
        new, rules, warnings = self.apply(code, SEMI_STYLE)
        self.assertIn('x = 1; y = 2', new)
        self.assertTrue(any('한 줄로 결합' in r for r in rules))
        self.assertFalse(any('줄바꿈으로 분리' in r for r in rules))

    def test_join_two_augmented_assignments(self):
        code = 'def f(xs):\n    total = 0\n    count = 0\n    for x in xs:\n        total += x\n        count += 1\n    return total, count\n'
        new, _, _ = self.apply(code, SEMI_STYLE)
        self.assertIn('total = 0; count = 0', new)
        self.assertIn('total += x; count += 1', new)

    def test_join_does_not_cross_blank_line(self):
        code = 'x = 1\n\ny = 2\n'
        new, rules, _ = self.apply(code, SEMI_STYLE)
        self.assertEqual(code, new)
        self.assertFalse(rules)

    def test_join_does_not_cross_comment(self):
        code = 'x = 1\n# important\ny = 2\n'
        new, rules, _ = self.apply(code, SEMI_STYLE)
        self.assertEqual(code, new)
        self.assertFalse(rules)

    def test_join_does_not_erase_inline_comment(self):
        code = 'x = 1 # important\ny = 2\n'
        new, rules, _ = self.apply(code, SEMI_STYLE)
        self.assertEqual(code, new)
        self.assertFalse(rules)

    def test_join_does_not_cross_function_boundary(self):
        code = 'def a():\n    x=1\n    return x\ndef b():\n    x=2\n    return x\n'
        new, _, _ = self.apply(code, SEMI_STYLE)
        self.assertNotIn('return x; def b()', new)

    def test_join_does_not_join_print_lines(self):
        code = 'print(1)\nprint(2)\n'
        new, rules, _ = self.apply(code, SEMI_STYLE)
        self.assertEqual(code, new)
        self.assertFalse(rules)

    def test_join_does_not_join_control_flow(self):
        code = 'x = 1\nif x:\n    y = 2\n'
        new, rules, _ = self.apply(code, SEMI_STYLE)
        self.assertEqual(code, new)
        self.assertFalse(rules)

    def test_join_does_not_touch_multiline_assignment(self):
        code = 'x = [\n    1,\n    2,\n]\ny = 2\n'
        new, rules, _ = self.apply(code, SEMI_STYLE)
        self.assertEqual(code, new)
        self.assertFalse(rules)

    def test_join_does_not_make_overlong_line(self):
        code = 'this_variable_name_is_extremely_long_and_already_verbose = "' + ('a' * 75) + '"\ny = 2\n'
        new, rules, _ = self.apply(code, SEMI_STYLE)
        self.assertEqual(code, new)
        self.assertFalse(rules)

    def test_join_avoids_multistatement_mixed(self):
        code = 'a = 1; b = 2\nc = 3\n'
        new, _, _ = self.apply(code, SEMI_STYLE)
        self.assertEqual(plain_ast(new), plain_ast(code))

    def test_join_profile_without_assignments_warns(self):
        code = 'print(1)\nprint(2)\n'
        new, _, warnings = self.apply(code, SEMI_STYLE)
        self.assertEqual(new, code)
        self.assertTrue(any('인접 대입문' in w for w in warnings))

    def test_join_and_split_fixed_sample_runtime_output(self):
        code = ('def f(xs):\n'
                '    total = 0\n'
                '    count = 0\n'
                '    for x in xs:\n'
                '        total += x\n'
                '        count += 1\n'
                '    return total, count\n'
                'print(f([1, 2, 3]))\n')
        joined, _, _ = self.apply(code, SEMI_STYLE)
        split, _, _ = self.apply(joined, SPLIT_STYLE)
        import contextlib
        import io
        values = []
        for sample in (code, joined, split):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exec(compile(sample, '<fixed regression test>', 'exec'), {})
            values.append(stdout.getvalue())
        self.assertEqual(values, ['(6, 3)\n'] * 3)

    def test_long_code_with_320_assignments_joined(self):
        code = ('def f():\n' + ''.join(f'    a{i} = {i}\n' for i in range(320)) +
                '    return a319\n')
        new, rules, _ = self.apply(code, SEMI_STYLE)
        self.assertIn('a0 = 0; a1 = 1', new)
        self.assertTrue(rules)

    def test_join_hash_in_string_literal(self):
        code = 'x = "#hashtag"\ny = "value"\n'
        new, _, _ = self.apply(code, SEMI_STYLE)
        self.assertIn('x = "#hashtag"; y = "value"', new)

    def test_blank_line_run_collapsed(self):
        code = 'x = 1\n\n\n\n\ny = 2\n'
        new, rules, _ = self.apply(code, SPLIT_STYLE)
        self.assertIn('x = 1\n\ny = 2', new)
        self.assertTrue(any('빈 줄' in r for r in rules))

    def test_one_blank_line_not_deleted(self):
        code = 'x = 1\n\ny = 2\n'
        new, _, _ = self.apply(code, SPLIT_STYLE)
        self.assertEqual(code, new)

    def test_multiline_triple_string_blank_lines_kept(self):
        code = 'x = """hello\n\n\n\nworld"""\ny = 2\n'
        new, _, _ = self.apply(code, SPLIT_STYLE)
        self.assertIn('hello\n\n\n\nworld', new)

    def test_bracket_expression_kept(self):
        code = 'items = [\n    1,\n\n\n    2,\n]\n'
        new, _, _ = self.apply(code, SPLIT_STYLE)
        self.assertIn('1,\n\n\n    2', new)

    def test_long_parenthesized_continuation_kept(self):
        code = 'def f():\n    result = (\n        12 +\n        34\n    )\n    return result\n'
        new, _, _ = self.apply(code, TWO_SPACE)
        self.assertIn('        12 +', new)
        self.assertIn('\n  return result\n', new)

    def test_explicit_backslash_continuation_kept(self):
        code = 'def f():\n    x = 10 + \\\n        20\n    return x\n'
        new, _, _ = self.apply(code, TWO_SPACE)
        self.assertIn('        20', new)
        self.assertIn('\n  return x\n', new)

    def test_empty_code_no_crash(self):
        new, rules, warnings = self.apply('', SPLIT_STYLE)
        self.assertEqual(new, '')
        self.assertFalse(rules)

    def test_unchanged_code_no_false_success(self):
        code = 'def f():\n    x = 1\n    return x\n'
        new, rules, _ = self.apply(code, FOUR_SPACE)
        self.assertEqual(new, code)
        self.assertFalse(rules)

    def test_none_profile_no_change(self):
        code = 'x = 1\n'
        self.assertEqual(apply_saved_formatting_style(code, None), (code, [], []))

    def test_invalid_profile_version_skipped(self):
        code = 'x = 1\n'
        new, rules, warnings = self.apply(code, {'version': 100})
        self.assertEqual(new, code)
        self.assertFalse(rules)
        self.assertTrue(warnings)

    def test_empty_profile_skipped(self):
        new, rules, warnings = self.apply('x=1', {})
        self.assertEqual(new, 'x=1')
        self.assertFalse(rules)
        self.assertTrue(warnings)

    def test_invalid_unit_boolean_rejected(self):
        p = dict(FOUR_SPACE)
        p['indentation'] = dict(FOUR_SPACE['indentation'], unit_columns=True)
        new, _, warnings = self.apply('x=1', p)
        self.assertEqual(new, 'x=1')
        self.assertTrue(warnings)

    def test_invalid_unit_negative_rejected(self):
        p = dict(FOUR_SPACE)
        p['indentation'] = dict(FOUR_SPACE['indentation'], unit_columns=-2)
        _, _, warnings = self.apply('x=1', p)
        self.assertTrue(warnings)

    def test_invalid_kind_rejected(self):
        p = dict(FOUR_SPACE)
        p['indentation'] = dict(FOUR_SPACE['indentation'], kind='unknown')
        _, _, warnings = self.apply('x=1', p)
        self.assertTrue(warnings)

    def test_mixed_saved_indent_skipped(self):
        p = dict(FOUR_SPACE)
        p['indentation'] = dict(FOUR_SPACE['indentation'], kind='mixed')
        _, _, warnings = self.apply('x=1', p)
        self.assertTrue(any('혼용' in w for w in warnings))

    def test_malformed_line_layout_rejected(self):
        p = dict(FOUR_SPACE)
        p['line_layout'] = None
        _, _, warnings = self.apply('x=1', p)
        self.assertTrue(warnings)

    def test_older_style_profile_missing(self):
        code = 'x = 1'
        self.assertEqual(apply_saved_formatting_style(code, None)[0], code)

    def test_large_code_300_lines(self):
        lines = ['def process(x):', '    score = 0']
        lines.extend('    score += ' + str(i) for i in range(300))
        lines.append('    return score + x')
        code = '\n'.join(lines) + '\n'
        new, rules, _ = self.apply(code, TWO_SPACE)
        self.assertGreater(len(new.splitlines()), 300)
        self.assertIn('  score += 299', new)
        self.assertTrue(rules)

    def test_unicode_identifier(self):
        code = 'def 계산():\n    값 = 2\n    return 값\n'
        new, _, _ = self.apply(code, TWO_SPACE)
        self.assertIn('  값 = 2', new)

    def test_crlf_source_maintained(self):
        code = 'def f():\r\n    x = 1\r\n    return x\r\n'
        new, _, _ = self.apply(code, TWO_SPACE)
        self.assertIn('\r\n  x = 1\r\n', new)

    def test_no_runtime_execution(self):
        code = 'open("must_not_exist.txt", "w").write("danger")\n'
        with patch('builtins.open', side_effect=AssertionError('executed user code')):
            new, _, _ = self.apply(code, SPLIT_STYLE)
        self.assertEqual(new, code)

    def test_idempotence(self):
        code = 'def f():\n    x=1; y=2\n    return x + y\n'
        first, rules, _ = self.apply(code, TWO_SPACE)
        self.assertTrue(rules)
        second, second_rules, _ = self.apply(first, TWO_SPACE)
        self.assertEqual(first, second)
        self.assertFalse(second_rules)

    def test_semicolon_splitting_does_not_touch_dictionaries(self):
        code = 'x = {"a": ";", "b": ":"}; y = 1\n'
        new, _, _ = self.apply(code, SPLIT_STYLE)
        self.assertIn('x = {"a": ";", "b": ":"}\ny = 1', new)

    def test_unverified_indentation_conversion_rejected(self):
        code = 'def f():\n    x = 1\n    return x\n'
        p = dict(TWO_SPACE)
        p['indentation'] = dict(TWO_SPACE['indentation'], unit_columns=6)
        new, _, _ = self.apply(code, p)
        self.assertIn('      x = 1', new)

    def test_formatting_does_not_change_string_escape_value(self):
        code = 'def f():\n    x = "\\t tab \\n newline"\n    return x\n'
        new, _, _ = self.apply(code, TWO_SPACE)
        self.assertEqual(ast.literal_eval(ast.parse(new).body[0].body[0].value), '\t tab \n newline')

    def test_profile_is_json_serializable(self):
        json.dumps(profile('def f():\n    return 1\n'))

    def test_ast_same_if_invisible_comment(self):
        code = 'def f():\n    # comment\n    x=3; y=4\n    return x + y\n'
        new, _, _ = self.apply(code, SPLIT_STYLE)
        self.assertEqual(plain_ast(new), plain_ast(code))

    def test_newline_in_string_not_rewritten(self):
        code = 'def f():\n    return """hi\nthere"""\n'
        new, _, _ = self.apply(code, TWO_SPACE)
        self.assertEqual(plain_ast(new), plain_ast(code))

    def test_target_tabs_dont_modify_continuation(self):
        p = profile('def f():\n\tx = 1\n\treturn x\n')
        code = 'def f():\n    value = (\n        1 +\n        2\n    )\n    return value\n'
        new, _, _ = self.apply(code, p)
        self.assertIn('\n\treturn value', new)
        self.assertIn('\n        1 +\n', new)


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('capstone_fmt_apply_installer', INSTALLER_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        cls.installer = module

    def make_project(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        needed = [
            'backend/app/services/style_format_profile_service.py',
            'backend/app/services/style_apply_service.py',
            'frontend/lib/codingStyleFactory.ts',
            'frontend/types/analysis.ts',
            'backend/app/schemas/style_apply.py',
            'backend/app/api/routes/style_apply.py',
        ]
        for rel in needed:
            f = root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text('# installed\n')
        (root / 'frontend/lib/codingStyleFactory.ts').write_text('const formatting_style = true;\n')
        (root / 'backend/app/schemas/style_apply.py').write_text('''from typing import Any, Dict, List, Optional
from pydantic import BaseModel
class CodingStylePayload(BaseModel):
    id: str
    created_at: str

class Dummy(BaseModel):
    pass
''')
        (root / 'backend/app/api/routes/style_apply.py').write_text('''from fastapi import APIRouter
from app.services.style_apply_service import apply_coding_style
router = APIRouter()

def apply_style_api(request):
    (
       transformed_code,
       summary,
       applied_rules,
       warnings,
       final_diff,
       execution_verification,
    ) = apply_coding_style(code=request.code, style=request.style.model_dump())

    if False:
        pass

        return StyleApplyResponse(
            success=True,
            transformed_code=transformed_code,
        )
''')
        return tmp, root

    def test_patch_schema_valid_ast(self):
        source = 'from typing import Any, Dict, List, Optional\nfrom pydantic import BaseModel\nclass CodingStylePayload(BaseModel):\n    created_at: str\n'
        new = self.installer.patch_schema(source)
        ast.parse(new)
        self.assertIn('formatting_style: Optional[Dict[str, Any]] = None', new)

    def test_patch_schema_does_not_change_other_classes(self):
        source = 'from typing import Any, Dict, Optional\nclass Other:\n    created_at: str\nclass CodingStylePayload:\n    created_at: str\n'
        new = self.installer.patch_schema(source)
        self.assertEqual(new.count('formatting_style:'), 1)

    def test_patch_schema_idempotence(self):
        source = 'class CodingStylePayload:\n    created_at: str\n'
        first = self.installer.patch_schema(source)
        self.assertEqual(first, self.installer.patch_schema(first))

    def test_patch_route_valid_ast(self):
        source = 'from app.services.style_apply_service import apply_coding_style\ndef apply_style_api(request):\n        return StyleApplyResponse(\n            success=True,\n        )\n'
        new = self.installer.patch_route(source)
        ast.parse(new)
        self.assertIn('apply_saved_formatting_style(', new)

    def test_patch_route_idempotence(self):
        source = 'from app.services.style_apply_service import apply_coding_style\ndef apply_style_api(request):\n        return StyleApplyResponse(\n            success=True,\n        )\n'
        first = self.installer.patch_route(source)
        self.assertEqual(first, self.installer.patch_route(first))

    def test_install_backups_and_changes(self):
        tmp, root = self.make_project()
        try:
            backup = root / 'safe_backup'
            changed = self.installer.install(root, backup)
            self.assertEqual(len(changed), 3)
            self.assertEqual(len(self.installer.plan(root)), 0)
            self.assertTrue((backup / 'backend/app/schemas/style_apply.py').exists())
            self.assertTrue((backup / 'backend/app/api/routes/style_apply.py').exists())
        finally:
            tmp.cleanup()

    def test_install_no_partial_write_if_bad_route(self):
        tmp, root = self.make_project()
        try:
            route = root / 'backend/app/api/routes/style_apply.py'
            route.write_text('def not_route():\n    pass\n')
            schema = root / 'backend/app/schemas/style_apply.py'
            old = schema.read_bytes()
            with self.assertRaises(self.installer.InstallationError):
                self.installer.install(root)
            self.assertEqual(schema.read_bytes(), old)
        finally:
            tmp.cleanup()

    def test_missing_prior_save_connection_rejected(self):
        tmp, root = self.make_project()
        try:
            (root / 'frontend/lib/codingStyleFactory.ts').write_text('// no saved profile\n')
            with self.assertRaises(self.installer.InstallationError):
                self.installer.plan(root)
        finally:
            tmp.cleanup()

    def test_missing_schema_rejected(self):
        tmp, root = self.make_project()
        try:
            (root / 'backend/app/schemas/style_apply.py').unlink()
            with self.assertRaises(self.installer.InstallationError):
                self.installer.plan(root)
        finally:
            tmp.cleanup()

    def test_partial_install_rejected(self):
        tmp, root = self.make_project()
        try:
            schema = root / 'backend/app/schemas/style_apply.py'
            schema.write_text(self.installer.patch_schema(schema.read_text(encoding='utf-8')), encoding='utf-8')
            with self.assertRaises(self.installer.InstallationError):
                self.installer.plan(root)
        finally:
            tmp.cleanup()

    def test_install_twice_no_change(self):
        tmp, root = self.make_project()
        try:
            self.installer.install(root, root / 'backups')
            self.assertEqual(self.installer.install(root, root / 'backups'), ['이미 설치되어 있습니다. 변경한 파일이 없습니다.'])
        finally:
            tmp.cleanup()

    def test_frontend_unmodified(self):
        tmp, root = self.make_project()
        try:
            frontend = root / 'frontend/lib/codingStyleFactory.ts'
            before = frontend.read_bytes()
            self.installer.install(root, root / 'backups')
            self.assertEqual(frontend.read_bytes(), before)
        finally:
            tmp.cleanup()

    @unittest.skipUnless(HAS_PYDANTIC, "로컬 Python에 pydantic 없음: Docker 백엔드에서 API 통합 테스트를 실행하세요.")
    def test_previous_saved_without_formatting_supported(self):
        source = '''from typing import Dict, Optional, Any
from pydantic import BaseModel
class CodingStylePayload(BaseModel):
    id: str
    created_at: str
'''
        exec(self.installer.patch_schema(source), namespace := {})
        namespace['CodingStylePayload'].model_rebuild(_types_namespace=namespace)
        style = namespace['CodingStylePayload'](id='old', created_at='now')
        self.assertIsNone(style.formatting_style)

    @unittest.skipUnless(HAS_PYDANTIC, "로컬 Python에 pydantic 없음: Docker 백엔드에서 API 통합 테스트를 실행하세요.")
    def test_nested_saved_formatting_roundtrip(self):
        source = '''from typing import Dict, Optional, Any
from pydantic import BaseModel
class CodingStylePayload(BaseModel):
    id: str
    created_at: str
'''
        exec(self.installer.patch_schema(source), namespace := {})
        namespace['CodingStylePayload'].model_rebuild(_types_namespace=namespace)
        style = namespace['CodingStylePayload'](id='new', created_at='now', formatting_style=TWO_SPACE)
        self.assertEqual(style.model_dump()['formatting_style']['indentation']['unit_columns'], 2)


@unittest.skipUnless(HAS_PYDANTIC, "로컬 Python에 pydantic 없음: Docker 백엔드에서 API 통합 테스트를 실행하세요.")
class RouteBridgeTests(unittest.TestCase):
    """Exercise the installed bridge at the actual API return boundary."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('capstone_fmt_route_installer', INSTALLER_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        cls.installer = module

    def bridge(self, code, fmt, verifier=None, warnings=None):
        from unittest.mock import patch
        schema_source = (
            'from typing import Any, Dict, Optional\n'
            'from pydantic import BaseModel\n'
            'class CodingStylePayload(BaseModel):\n'
            '    id: str\n'
            '    created_at: str\n'
        )
        schema_namespace = {}
        exec(self.installer.patch_schema(schema_source), schema_namespace)
        klass = schema_namespace['CodingStylePayload']
        klass.model_rebuild(_types_namespace=schema_namespace)
        style = klass(id='style', created_at='today', formatting_style=fmt)

        def mock_apply(**kwargs):
            return (code, '태그 변환 결과:', [], (warnings or []).copy(), {}, verifier)
        module = types.ModuleType('app.services.style_apply_service')
        module.apply_coding_style = mock_apply
        route_source = (
            'from app.services.style_apply_service import apply_coding_style\n'
            'def apply_style_api(request):\n'
            '    transformed_code, summary, applied_rules, warnings, final_diff, execution_verification = apply_coding_style(' 
            'code=request.code, style=request.style.model_dump())\n'
            '    if True:\n'
            '        return StyleApplyResponse(\n'
            '            success=True,\n'
            '            transformed_code=transformed_code,\n'
            '            applied_rules=applied_rules,\n'
            '            warnings=warnings,\n'
            '            summary=summary,\n'
            '        )\n'
        )
        source = self.installer.patch_route(route_source)
        namespace = {'StyleApplyResponse': lambda **kwargs: types.SimpleNamespace(**kwargs)}
        with patch.dict(sys.modules, {'app.services.style_apply_service': module}):
            exec(source, namespace)
            request = types.SimpleNamespace(code=code, style=style)
            return namespace['apply_style_api'](request)

    def test_profile_passes_through_schema_and_route(self):
        code = 'def f():\n    x=1\n    return x\n'
        res = self.bridge(code, TWO_SPACE)
        self.assertIn('\n  x=1\n', res.transformed_code)
        self.assertTrue(any('들여쓰기' in rule for rule in res.applied_rules))
        self.assertIn('AST', res.summary)

    def test_legacy_style_no_formatting_no_change(self):
        code = 'def f():\n    x=1\n    return x\n'
        res = self.bridge(code, None)
        self.assertEqual(res.transformed_code, code)
        self.assertFalse(res.applied_rules)

    def test_different_verifier_skips_format(self):
        code = 'def f():\n    x=1\n    return x\n'
        res = self.bridge(code, TWO_SPACE, {'status': 'different'})
        self.assertEqual(res.transformed_code, code)
        self.assertTrue(any('생략' in msg for msg in res.warnings))

    def test_rolled_back_not_verified_skips_format(self):
        code = 'def f():\n    x=1\n    return x\n'
        res = self.bridge(code, TWO_SPACE, {'status': 'not_verified'},
                          ['실행 동등성이 검증되지 않아 전체 변환을 취소하고 원본을 유지했습니다.'])
        self.assertEqual(res.transformed_code, code)
        self.assertTrue(any('서식 적용도 생략' in msg for msg in res.warnings))

    def test_format_rule_is_real_and_visible_in_response(self):
        code = 'def f():\n    x=1; y=2\n    return x+y\n'
        res = self.bridge(code, SPLIT_STYLE)
        self.assertIn('x=1\n    y=2', res.transformed_code)
        self.assertIn('적용 완료:', ' | '.join(res.applied_rules))


if __name__ == '__main__':
    unittest.main()
