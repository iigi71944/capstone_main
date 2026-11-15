"""Regression tests for local plans on 80-300+ line Python programs."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.services.style_large_code_service import (
    MAX_LONG_CODE_LINES,
    MIN_LONG_CODE_LINES,
    _safe_scopes,
    apply_scoped_style_to_large_code,
)

ACTION = 'create_return_structure'
OTHER = 'create_conditional_expression'


def fake_diff(*, style: dict, code: str) -> dict:
    return {'code': code}


def fake_plan(diff: dict) -> dict:
    if 'return number + 0' in diff['code']:
        return {'actions': [{'action': ACTION, 'tag': 'return문', 'reason': '개별 함수'}]}
    return {'actions': []}


def fake_transform(source: str) -> str:
    return source.replace('return number + 0', 'return number')


def make_code(number: int = 25, *, prefix: str = '') -> str:
    chunks = [prefix] if prefix else []
    for i in range(number):
        chunks.append(f'''def calculate_{i}(number):
    # 각 함수의 원본 주석 {i}
    temp = number * 2
    return number + 0
''')
    chunks.append('print(calculate_0(3))\n')
    return '\n'.join(chunks)


def apply(code, *, plan=fake_plan, transform=fake_transform, style=None):
    return apply_scoped_style_to_large_code(
        code=code, style=style or {}, compare_style=fake_diff,
        build_plan=plan,
        get_transformer=lambda action: transform if action == ACTION else None,
    )


class LargeCodeScopeTests(unittest.TestCase):
    def test_100_plus_lines_all_functions_are_scoped(self):
        source = make_code(26)
        self.assertGreaterEqual(len(source.splitlines()), 100)
        result, applied, notes = apply(source)
        self.assertEqual(26, len(applied))
        self.assertEqual(0, result.count('return number + 0'))
        self.assertEqual(26, result.count('return number\n'))
        self.assertIn('# 각 함수의 원본 주석 0', result)
        self.assertIn('# 각 함수의 원본 주석 25', result)
        self.assertEqual(3, self._run(result))
        self.assertEqual(3, self._run(source))
        self.assertTrue(notes)

    def _run(self, text: str) -> int:
        import io
        from contextlib import redirect_stdout
        output = io.StringIO()
        with redirect_stdout(output):
            exec(compile(text, '<test>', 'exec'), {})
        return int(output.getvalue().strip())

    def test_300_plus_lines(self):
        source = make_code(64)
        self.assertGreater(len(source.splitlines()), 300)
        result, actions, warnings = apply(source)
        self.assertEqual(64, len(actions))
        self.assertEqual(3, self._run(result))
        self.assertEqual(64, result.count('return number\n'))
        self.assertFalse('return number + 0' in result)

    def test_preserves_unrelated_lines_exactly(self):
        source = make_code(25, prefix='# top comment\nUNRELATED = "hello"\n\n')
        result, _, _ = apply(source)
        self.assertTrue(result.startswith('# top comment\nUNRELATED = "hello"\n\n'))
        self.assertIn('print(calculate_0(3))\n', result)

    def test_scoped_steps_are_idempotent(self):
        source = make_code(25)
        first, applied, _ = apply(source)
        second, again, _ = apply(first)
        self.assertTrue(applied)
        self.assertFalse(again)
        self.assertEqual(first, second)

    def test_short_files_keep_existing_behavior(self):
        source = make_code(3)
        self.assertLess(len(source.splitlines()), MIN_LONG_CODE_LINES)
        self.assertEqual((source, [], []), apply(source))

    def test_2000_line_cap(self):
        source = make_code(450)
        self.assertGreater(len(source.splitlines()), MAX_LONG_CODE_LINES)
        result, actions, warnings = apply(source)
        self.assertEqual(source, result)
        self.assertFalse(actions)
        self.assertTrue(warnings)

    def test_scopes_cap(self):
        source = make_code(81)
        result, actions, warnings = apply(source)
        self.assertEqual(source, result)
        self.assertFalse(actions)
        self.assertTrue(warnings)

    def test_class_methods_with_four_space_indentation(self):
        source = ('class Calculator:\n'
                  '    def first(self, number):\n'
                  '        return number + 0\n\n'
                  '    def second(self, number):\n'
                  '        return number + 0\n\n')
        source += '\n'.join('# padding' for _ in range(90)) + '\n'
        result, actions, _ = apply(source)
        self.assertEqual(2, len(actions))
        self.assertIn('class Calculator:\n    def first(self, number):\n        return number\n', result)
        self.assertEqual(5, self._run(result + '\nprint(Calculator().second(5))\n'))

    def test_class_methods_with_two_space_indentation(self):
        source = ('class Calculator:\n'
                  '  def first(self, number):\n'
                  '    return number + 0\n')
        source += '\n' + '\n'.join('# padding' for _ in range(85)) + '\n'
        result, actions, _ = apply(source)
        self.assertEqual(1, len(actions))
        self.assertIn('  def first(self, number):\n    return number\n', result)
        ast.parse(result)

    def test_tab_indented_class_methods(self):
        source = 'class C:\n\tdef f(self, number):\n\t\treturn number + 0\n'
        source += '\n' + '\n'.join('# padding' for _ in range(80)) + '\n'
        result, actions, _ = apply(source)
        self.assertEqual(1, len(actions))
        self.assertIn('\t\treturn number\n', result)

    def test_decorated_function_skipped(self):
        code = 'def decor(f): return f\n@decor\ndef f(number):\n    return number + 0\n'
        code += '\n'.join('# padding' for _ in range(90))
        result, actions, _ = apply(code)
        self.assertEqual(code, result)
        self.assertFalse(actions)

    def test_nested_definition_skipped(self):
        code = 'def f(number):\n    def inner():\n        return number + 0\n    return inner()\n'
        code += '\n'.join('# padding' for _ in range(85))
        self.assertEqual(code, apply(code)[0])

    def test_dynamic_locals_skipped(self):
        code = 'def f(number):\n    old = locals()\n    return number + 0\n'
        code += '\n'.join('# padding' for _ in range(85))
        self.assertEqual(code, apply(code)[0])

    def test_global_skipped(self):
        code = 'def f(number):\n    global counter\n    return number + 0\n'
        code += '\n'.join('# padding' for _ in range(85))
        self.assertEqual(code, apply(code)[0])

    def test_async_skipped(self):
        code = 'async def f(number):\n    return number + 0\n'
        code += '\n'.join('# padding' for _ in range(85))
        self.assertEqual(code, apply(code)[0])

    def test_multiline_strings_skipped(self):
        code = 'def f(number):\n    message = """hello\n    world"""\n    return number + 0\n'
        code += '\n'.join('# padding' for _ in range(85))
        self.assertEqual(code, apply(code)[0])

    def test_comment_dropped_by_transformer_skips_unit(self):
        source = make_code(25)
        result, actions, _ = apply(source, transform=lambda s: fake_transform(s).replace('    # 각 함수의 원본 주석', '    # 제거된 주석'))
        self.assertEqual(source, result)
        self.assertFalse(actions)

    def test_changed_string_literal_skips_unit(self):
        source = make_code(25).replace('temp = number * 2', 'temp = "안녕"')
        result, actions, _ = apply(source, transform=lambda s: fake_transform(s).replace('"안녕"', '"잘가"'))
        self.assertEqual(source, result)
        self.assertFalse(actions)

    def test_changed_function_signature_skips(self):
        source = make_code(25)
        result, actions, _ = apply(source, transform=lambda s: fake_transform(s).replace('(number)', '(number, another=0)'))
        self.assertEqual(source, result)
        self.assertFalse(actions)

    def test_invalid_syntax_from_transform_skips(self):
        source = make_code(25)
        self.assertEqual(source, apply(source, transform=lambda s: s.replace('return number + 0', 'return ('))[0])

    def test_new_top_level_statement_skips(self):
        source = make_code(25)
        result, actions, _ = apply(source, transform=lambda s: fake_transform(s) + '\nprint("side effect")')
        self.assertEqual(source, result)
        self.assertFalse(actions)

    def test_transformer_exception_skips(self):
        source = make_code(25)
        def fail(s):
            raise RuntimeError('failure')
        self.assertEqual(source, apply(source, transform=fail)[0])

    def test_non_string_transformer_skips(self):
        source = make_code(25)
        self.assertEqual(source, apply(source, transform=lambda s: None)[0])

    def test_no_changed_ast_not_reported(self):
        source = make_code(25)
        result, actions, _ = apply(source, transform=lambda s: s.replace('return number + 0', 'return (number + 0)'))
        self.assertEqual(source, result)
        self.assertFalse(actions)

    def test_new_unsafe_action_not_permitted(self):
        source = make_code(25)
        plan = lambda d: {'actions': [{'action': 'create_function_structure'}]}
        self.assertEqual(source, apply(source, plan=plan)[0])

    def test_unsupported_action_skipped_but_next_safe_one_can_run(self):
        source = make_code(25)
        plan = lambda d: {'actions': [{'action': 'create_function_structure'}, {'action': ACTION}]}
        result, applied, _ = apply(source, plan=plan)
        self.assertEqual(25, len(applied))
        self.assertNotEqual(source, result)

    def test_one_action_only_per_method(self):
        source = make_code(25)
        plan = lambda d: {'actions': [{'action': ACTION}, {'action': OTHER}]}
        result, applied, _ = apply(source, plan=plan)
        self.assertEqual(25, len(applied))
        self.assertTrue(all(item['action'] == ACTION for item in applied))

    def test_unparsable_target_is_left_intact(self):
        source = 'def broken(:\n' + '\n'.join('# pad' for _ in range(90))
        self.assertEqual((source, [], []), apply(source))

    def test_multibyte_characters_not_damaged(self):
        source = make_code(25).replace('temp = number * 2', 'temp = "한글/🌿"')
        result, applied, _ = apply(source)
        self.assertEqual(25, len(applied))
        self.assertEqual(25, result.count('"한글/🌿"'))

    def test_original_without_final_newline(self):
        source = make_code(25).rstrip('\n')
        result, actions, _ = apply(source)
        self.assertEqual(25, len(actions))
        self.assertFalse(result.endswith('\n'))

    def test_reject_try_to_change_docstring(self):
        source = make_code(25).replace('    # 각 함수의 원본 주석 0', '    """docstring"""\n    # 각 함수의 원본 주석 0')
        result, actions, _ = apply(source, transform=lambda s: fake_transform(s).replace('"""docstring"""', '"""different"""'))
        self.assertNotIn('different', result)
        self.assertEqual(24, len(actions))

    def test_real_list_transformer_on_160_lines(self):
        from app.services.improvement.safe_list_comprehension_service import (
            transform_for_append_to_list_comprehension,
        )
        source = self._real_code(20)
        result, actions, warnings = apply_scoped_style_to_large_code(
            code=source, style={}, compare_style=fake_diff,
            build_plan=self._real_plan,
            get_transformer=lambda name: transform_for_append_to_list_comprehension
                if name == 'create_safe_comprehension_collection' else None,
        )
        self.assertEqual(20, len(actions))
        self.assertEqual(0, result.count('output.append(value)'))
        self.assertEqual(self._run_lines(source), self._run_lines(result))

    def test_real_list_transformer_on_340_lines(self):
        from app.services.improvement.safe_list_comprehension_service import (
            transform_for_append_to_list_comprehension,
        )
        source = self._real_code(42)
        result, actions, warnings = apply_scoped_style_to_large_code(
            code=source, style={}, compare_style=fake_diff,
            build_plan=self._real_plan,
            get_transformer=lambda name: transform_for_append_to_list_comprehension
                if name == 'create_safe_comprehension_collection' else None,
        )
        self.assertEqual(42, len(actions))
        self.assertEqual(self._run_lines(source), self._run_lines(result))

    def _real_code(self, count):
        sections = [
            'def already(values):\n'
            '    return [v for v in values if v >= 0]\n',
        ]
        for i in range(count):
            sections.append(
                f'def keep_{i}(values):\n'
                '    output = []\n'
                '    for value in values:\n'
                '        if value >= 0:\n'
                '            output.append(value)\n'
                '    return output\n'
            )
        sections.append('print(keep_0([-3, 0, 2, 7]))\n')
        return '\n\n'.join(sections)

    def _real_plan(self, diff):
        if 'output.append(value)' in diff['code']:
            return {'actions': [{
                'tag': '리스트 컴프리헨션',
                'action': 'create_safe_comprehension_collection',
                'reason': 'saved style',
            }]}
        return {'actions': []}

    def _run_lines(self, source):
        import io
        from contextlib import redirect_stdout
        output = io.StringIO()
        with redirect_stdout(output):
            exec(compile(source, '<test>', 'exec'), {})
        return output.getvalue()

    def test_crlf_source_keeps_crlf(self):
        source = make_code(25).replace('\n', '\r\n')
        result, actions, _ = apply(source)
        self.assertEqual(25, len(actions))
        self.assertEqual(result.count('\n'), result.count('\r\n'))
        self.assertEqual(3, self._run(result))

    def test_annotated_signature_preserved(self):
        source = make_code(25).replace('(number):', '(number: int) -> int:')
        result, actions, _ = apply(source)
        self.assertEqual(25, len(actions))
        self.assertIn('def calculate_0(number: int) -> int:', result)
        self.assertEqual(3, self._run(result))

    def test_standalone_function_docstring_preserved(self):
        source = make_code(25).replace(
            '    # 각 함수의 원본 주석 0',
            '    """알림: 원본 독스트링"""\n    # 각 함수의 원본 주석 0',
        )
        result, actions, _ = apply(source)
        self.assertEqual(25, len(actions))
        self.assertIn('"""알림: 원본 독스트링"""', result)
        self.assertEqual(3, self._run(result))

    def test_class_body_not_scoped(self):
        source = ('class C:\n    data = 1\n\n' +
                  '\n'.join('# pad' for _ in range(85)) + '\n')
        self.assertEqual((source, [], []), apply(source))

    def test_action_order_matches_source_order(self):
        source = make_code(25)
        _, actions, _ = apply(source)
        self.assertEqual('calculate_0', actions[0]['scope'])
        self.assertEqual('calculate_24', actions[-1]['scope'])


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        toolpath = Path(__file__).resolve().parents[1] / 'tools' / 'install_large_code_scope.py'
        spec = importlib.util.spec_from_file_location('scope_installer_for_test', toolpath)
        cls.installer = importlib.util.module_from_spec(spec)
        import sys
        sys.modules[spec.name] = cls.installer
        spec.loader.exec_module(cls.installer)

    def _source(self):
        return '''def _normalize_code(code):\n    return code\n\ndef apply(code):\n    transformed_code = code\n    if _normalize_code(code) == _normalize_code(transformed_code):\n        transformed_code = code\n    must_rollback = changed and (\n        known_difference\n        or verifier_malformed\n            or (strict_runtime_validation and verification_status != "equivalent")\n    )\n'''

    def test_patch_is_idempotent(self):
        patched = self.installer.patch_service(self._source())
        self.assertIn(self.installer.MARK, patched)
        self.assertEqual(patched, self.installer.patch_service(patched))
        ast.parse(patched)

    def test_inserts_runtime_guard(self):
        patched = self.installer.patch_service(self._source())
        self.assertIn('(strict_runtime_validation or scoped_changes)', patched)

    def test_missing_anchor_fails_without_modification(self):
        with self.assertRaises(self.installer.InstallationError):
            self.installer.patch_service('def f(): pass')

    def test_duplicate_anchor_fails(self):
        source = self._source().replace('    if _normalize_code(code)',
                                        '    if _normalize_code(code)', 1)
        source += self._source()
        with self.assertRaises(self.installer.InstallationError):
            self.installer.patch_service(source)

    def test_partially_installed_fails(self):
        with self.assertRaises(self.installer.InstallationError):
            self.installer.patch_service('def f():\n    # CAPSTONE_LARGE_CODE_SCOPES_V1\n    pass\n')


class ServiceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from app.services import style_apply_service
        except ImportError as exc:
            raise unittest.SkipTest('전체 프로젝트 백엔드 의존성이 설치되어 있지 않습니다: ' + str(exc))
        cls.service = style_apply_service

    def _integrate(self, verification_status):
        service = self.service
        code = make_code(25)
        def plan(diff):
            if len(diff['code'].splitlines()) >= MIN_LONG_CODE_LINES:
                return {'actions': [], 'compare_only': []}
            return fake_plan(diff)
        verification = {
            'source': 'runtime', 'status': verification_status,
            'equivalent': True if verification_status == 'equivalent'
                else False if verification_status == 'different' else None,
            'message': 'integration test', 'function_verification': None,
        }
        final = {
            'missing_syntax_tags': [], 'missing_concept_tags': [],
            'target_analysis': {'syntax_tags': [], 'concept_tags': [], 'metrics': {}},
        }
        with patch.object(service, 'compare_style_with_target_code', side_effect=fake_diff), \
             patch.object(service, 'build_transform_plan', side_effect=plan), \
             patch.object(service, '_get_transform_function', return_value=fake_transform), \
             patch.object(service, 'verify_execution_equivalence', return_value=verification), \
             patch.object(service, 'compare_after_transform', return_value=final):
            return service.apply_coding_style(code, {'syntax_tags': [], 'concept_tags': [], 'metrics': {}})

    def test_equivalent_keeps_scoped_changes(self):
        result, summary, rules, warnings, diff, verification = self._integrate('equivalent')
        self.assertEqual(25, result.count('return number\n'))
        self.assertEqual(25, sum('긴 코드의 ' in x for x in rules))

    def test_not_verified_reverts_scoped_changes(self):
        result, summary, rules, warnings, diff, verification = self._integrate('not_verified')
        self.assertEqual(make_code(25), result)
        self.assertFalse(rules)
        self.assertTrue(any('취소' in x for x in warnings))

    def test_different_reverts_scoped_changes(self):
        result, summary, rules, warnings, diff, verification = self._integrate('different')
        self.assertEqual(make_code(25), result)
        self.assertFalse(rules)


if __name__ == '__main__':
    unittest.main()
