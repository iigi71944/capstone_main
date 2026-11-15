"""스타일 분석 주석 제외: 실행 코드 보존 및 실제 분석 진입점 연결 검증."""

import ast
import tempfile
import unittest
from pathlib import Path

from app.services.style_analysis_comment_filter_service import (
    without_analysis_comments,
)
from tools.install_style_comment_filter import (
    InstallationError,
    install,
    patched_source,
)


class AnalysisCommentFilterTests(unittest.TestCase):
    @staticmethod
    def parse(code, type_comments=False):
        return without_analysis_comments(ast.parse(code, type_comments=type_comments))

    def test_hash_comment_already_ignored(self):
        tree = self.parse("# 설명\nx = 3 # 메모\n")
        self.assertEqual(len(tree.body), 1)
        self.assertEqual(ast.unparse(tree).strip(), "x = 3")

    def test_module_docstring_single_quotes_removed(self):
        tree = self.parse("'''문서 메모'''\nx = 1\n")
        self.assertEqual(ast.unparse(tree), "x = 1")

    def test_module_docstring_double_quotes_removed(self):
        tree = self.parse('"""module doc"""\nx = 1\n')
        self.assertEqual(ast.unparse(tree), "x = 1")

    def test_standalone_late_triple_quoted_comment_removed(self):
        tree = self.parse("x=1\n'''두 번째 메모'''\ny=2\n")
        self.assertEqual(ast.unparse(tree), "x = 1\ny = 2")

    def test_function_docstring_removed(self):
        tree = self.parse("def f():\n    '''설명'''\n    return 3\n")
        self.assertEqual(ast.unparse(tree), "def f():\n    return 3")

    def test_async_function_docstring_removed(self):
        tree = self.parse("async def f():\n    '''설명'''\n    return 3\n")
        self.assertNotIn("설명", ast.unparse(tree))

    def test_class_docstring_removed(self):
        tree = self.parse("class A:\n    '''설명'''\n    x=1\n")
        self.assertEqual(ast.unparse(tree), "class A:\n    x = 1")

    def test_nested_class_function_docstrings_removed(self):
        tree = self.parse("class A:\n '''클래스'''\n def f(self):\n  '''메서드'''\n  return 1\n")
        self.assertNotIn("클래스", ast.unparse(tree))
        self.assertNotIn("메서드", ast.unparse(tree))

    def test_docstring_only_function_keeps_valid_body(self):
        tree = self.parse("def f():\n    '''설명'''\n")
        self.assertEqual(ast.unparse(tree), "def f():\n    pass")
        compile(tree, '<filtered>', 'exec')

    def test_docstring_only_class_keeps_valid_body(self):
        tree = self.parse("class A:\n    '''설명'''\n")
        self.assertEqual(ast.unparse(tree), "class A:\n    pass")
        compile(tree, '<filtered>', 'exec')

    def test_only_docstring_module_becomes_empty(self):
        tree = self.parse("'''설명'''\n")
        self.assertEqual(tree.body, [])
        compile(tree, '<filtered>', 'exec')

    def test_if_only_comment_keeps_valid_body(self):
        tree = self.parse("if True:\n '''메모'''\n")
        compile(tree, '<filtered>', 'exec')
        self.assertIn("pass", ast.unparse(tree))

    def test_for_only_comment_keeps_valid_body(self):
        tree = self.parse("for i in (1,):\n '''메모'''\n")
        compile(tree, '<filtered>', 'exec')

    def test_except_only_comment_keeps_valid_body(self):
        tree = self.parse("try:\n print(1)\nexcept Exception:\n '''메모'''\n")
        compile(tree, '<filtered>', 'exec')

    def test_match_only_comment_keeps_valid_body(self):
        tree = self.parse("match 1:\n case 1:\n  '''메모'''\n")
        compile(tree, '<filtered>', 'exec')

    def test_assigned_triple_string_preserved(self):
        tree = self.parse("description = '''필수 데이터'''\n")
        self.assertIn("필수 데이터", ast.unparse(tree))

    def test_returned_triple_string_preserved(self):
        tree = self.parse("def f():\n return '''결과'''\n")
        self.assertIn("결과", ast.unparse(tree))

    def test_argument_triple_string_preserved(self):
        tree = self.parse("print('''중요한 문자열''')\n")
        self.assertIn("중요한 문자열", ast.unparse(tree))

    def test_hash_in_string_preserved(self):
        tree = self.parse('x = "# 실제 텍스트"\n')
        self.assertIn("# 실제 텍스트", ast.unparse(tree))

    def test_nested_quote_in_string_preserved(self):
        tree = self.parse('text = "\\\'\\\'\\\' is data"\n')
        self.assertIn("is data", ast.unparse(tree))

    def test_fstring_expression_preserved(self):
        tree = self.parse("name='A'\nprint(f'Hello {name}')\n")
        self.assertIn("Hello", ast.unparse(tree))

    def test_original_ast_unmodified(self):
        original = ast.parse("'''첫 문서'''\nx=1\n")
        filtered = without_analysis_comments(original)
        self.assertEqual(ast.get_docstring(original), "첫 문서")
        self.assertIsNone(ast.get_docstring(filtered))
        self.assertIsNot(filtered, original)

    def test_real_code_keeps_line_information(self):
        original = ast.parse("'''문서'''\n# comment\nx=1\n")
        filtered = without_analysis_comments(original)
        self.assertEqual(filtered.body[0].lineno, 3)

    def test_type_ignore_removed(self):
        tree = self.parse("x = 1 # type: ignore\n", type_comments=True)
        self.assertEqual(tree.type_ignores, [])

    def test_type_comment_removed(self):
        tree = self.parse("x = 1 # type: int\n", type_comments=True)
        self.assertIsNone(tree.body[0].type_comment)

    def test_reject_non_ast_input(self):
        with self.assertRaises(TypeError):
            without_analysis_comments("x=3")

    def test_hash_comment_and_no_comment_equivalent(self):
        plain = self.parse("x=1\ny=2\n")
        commented = self.parse("# 설명\nx=1  # 내용\n# 설명\ny=2\n")
        self.assertEqual(ast.dump(plain, include_attributes=False), ast.dump(commented, include_attributes=False))

    def test_docstring_and_no_docstring_equivalent(self):
        plain = self.parse("def f():\n return 5\n")
        commented = self.parse("def f():\n '''설명'''\n return 5\n")
        self.assertEqual(ast.dump(plain, include_attributes=False), ast.dump(commented, include_attributes=False))

    def test_standalone_comment_does_not_create_call(self):
        filtered = self.parse("'''print('danger')'''\nresult = 1\n")
        self.assertFalse(any(isinstance(node, ast.Call) for node in ast.walk(filtered)))

    def test_return_and_assignment_strings_still_count_as_constants(self):
        filtered = self.parse("x='''data'''\ndef f():\n return '''result'''\n")
        self.assertEqual(
            sum(isinstance(n, ast.Constant) and isinstance(n.value, str) for n in ast.walk(filtered)),
            2,
        )


class InstallerTests(unittest.TestCase):
    FIXTURE_ANALYZE = (
        "from app.services.parser_service import parse_code\n"
        "def analyze(code):\n"
        "    tree = parse_code(code)\n"
        "    return tree\n"
    )
    FIXTURE_DIFF = (
        "from app.services.parser_service import parse_code\n"
        "def analyze_style(code):\n"
        "    tree = parse_code(code)\n"
        "    return tree\n"
    )

    def test_patch_analysis_route(self):
        patched, changed = patched_source(self.FIXTURE_ANALYZE)
        self.assertTrue(changed)
        self.assertIn("tree = without_analysis_comments(parse_code(code))", patched)
        self.assertIn("import without_analysis_comments", patched)
        compile(patched, '<analyze>', 'exec')

    def test_patch_idempotent(self):
        first, _ = patched_source(self.FIXTURE_ANALYZE)
        second, changed = patched_source(first)
        self.assertFalse(changed)
        self.assertEqual(first, second)

    def test_patch_unicode_before_call(self):
        content = "# 한글 메시지\n# 한글\ndef run(code):\n  분석트리 = parse_code(code)\n"
        patched, changed = patched_source(content)
        self.assertTrue(changed)
        compile(patched, '<unicode>', 'exec')
        self.assertIn("분석트리 = without_analysis_comments(parse_code(code))", patched)

    def test_patch_preserves_future_import(self):
        content = "'''module'''\nfrom __future__ import annotations\ndef run(code):\n return parse_code(code)\n"
        patched, _ = patched_source(content)
        compile(patched, '<future>', 'exec')
        self.assertTrue(patched.index("from __future__") < patched.index("import without_analysis_comments"))

    def test_patch_multiline_call(self):
        content = "tree = parse_code(\n    code,\n)\n"
        patched, _ = patched_source(content)
        compile(patched, '<multi>', 'exec')
        self.assertIn("without_analysis_comments(parse_code(", patched)

    def test_patch_two_calls(self):
        content = "a=parse_code('x=1')\nb=parse_code('y=2')\n"
        patched, _ = patched_source(content)
        self.assertEqual(patched.count("without_analysis_comments(parse_code("), 2)
        compile(patched, '<two>', 'exec')

    def test_patch_no_parse_code_fails(self):
        with self.assertRaises(InstallationError):
            patched_source("tree=ast.parse(code)\n")

    def test_installer_preflight_no_partial_change(self):
        with tempfile.TemporaryDirectory() as td:
            backend = Path(td)
            analyze = backend / 'app/api/routes/analyze.py'
            analyze.parent.mkdir(parents=True)
            analyze.write_text(self.FIXTURE_ANALYZE, encoding='utf-8')
            # style diff가 없으면 analyze 파일에도 쓰지 않아야 한다.
            with self.assertRaises(InstallationError):
                install(backend)
            self.assertEqual(analyze.read_text(encoding='utf-8'), self.FIXTURE_ANALYZE)

    def test_installer_both_entrypoints_and_backup(self):
        with tempfile.TemporaryDirectory() as td:
            backend = Path(td) / 'backend'
            for rel, content in [
                ('app/api/routes/analyze.py', self.FIXTURE_ANALYZE),
                ('app/services/style_diff_service.py', self.FIXTURE_DIFF),
            ]:
                file = backend / rel
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content, encoding='utf-8')
            backup = Path(td) / 'backup'
            report = install(backend, backup_root=backup)
            self.assertEqual(report['app/api/routes/analyze.py'], '수정')
            self.assertEqual(report['app/services/style_diff_service.py'], '수정')
            for rel in ['app/api/routes/analyze.py', 'app/services/style_diff_service.py']:
                self.assertTrue((backup / rel).exists())
                self.assertIn('without_analysis_comments(parse_code(', (backend / rel).read_text(encoding='utf-8'))
            report2 = install(backend, backup_root=backup)
            self.assertEqual(report2['app/api/routes/analyze.py'], '이미 적용됨')
            self.assertEqual(report2['app/services/style_diff_service.py'], '이미 적용됨')

    def test_install_aborts_on_nonmatching_route(self):
        with tempfile.TemporaryDirectory() as td:
            backend = Path(td)
            for rel, value in [
                ('app/api/routes/analyze.py', 'def analyze(code):\n return None\n'),
                ('app/services/style_diff_service.py', self.FIXTURE_DIFF),
            ]:
                path = backend / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value, encoding='utf-8')
            with self.assertRaises(InstallationError):
                install(backend)
            self.assertEqual((backend / 'app/services/style_diff_service.py').read_text(encoding='utf-8'), self.FIXTURE_DIFF)


class RealProjectWiringTests(unittest.TestCase):
    def test_existing_analysis_route_is_connected(self):
        backend = Path(__file__).resolve().parents[1]
        route = backend / 'app/api/routes/analyze.py'
        if not route.exists():
            self.skipTest('분석 라우트가 없는 독립 테스트 환경')
        self.assertIn('without_analysis_comments(', route.read_text(encoding='utf-8'))

    def test_existing_style_diff_is_connected(self):
        backend = Path(__file__).resolve().parents[1]
        diff = backend / 'app/services/style_diff_service.py'
        if not diff.exists():
            self.skipTest('스타일 비교 모듈이 없는 독립 테스트 환경')
        self.assertIn('without_analysis_comments(', diff.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
