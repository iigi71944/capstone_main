"""Regression tests for final-code execution output after saved formatting."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from app.services.style_format_profile_service import extract_formatting_style

ROOT = Path(__file__).resolve().parents[1]
NEW_INSTALLER = ROOT / 'tools/install_formatting_execution_fix.py'
# The formatting V1 installer belongs to the already-installed previous ZIP.
OLD_INSTALLER = ROOT / 'tools/install_formatting_apply.py'


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


V1_INSTALLER = load(OLD_INSTALLER, 'capstone_fmt_previous_installer_for_execution_test')
INSTALLER = load(NEW_INSTALLER, 'capstone_fmt_execution_fix_installer_test')

SOURCE = (
    'def calculate(numbers):\n'
    '    total = 0; count = 0\n'
    '    for number in numbers:\n'
    '        total += number; count += 1\n'
    '    return total, count\n'
    '\n'
    'print(calculate([1, 2, 3]))\n'
)
SPLIT_PROFILE = extract_formatting_style(
    'def f():\n  a = 1\n  b = 2\n  return a + b\n'
)


def check_result(status='equivalent'):
    return {
        'source': 'runtime',
        'status': status,
        'equivalent': {'equivalent': True, 'different': False, 'not_verified': None}[status],
        'message': 'test verdict',
        'original': {'success': True, 'stdout': '(6, 3)\n', 'stderr': '', 'blocked': False, 'timed_out': False, 'exit_code': 0},
        'transformed': {'success': True, 'stdout': '(6, 3)\n' if status != 'different' else 'wrong\n', 'stderr': '', 'blocked': False, 'timed_out': False, 'exit_code': 0},
    }


ROUTE_BEFORE_V1 = '''from app.services.style_apply_service import apply_coding_style

def apply_style_api(request):
    function_cases = request.function_cases
    (transformed_code, summary, applied_rules, warnings, final_diff,
     execution_verification) = apply_coding_style(
        code=request.code, style=request.style.model_dump(), function_cases=function_cases)
    if True:
        return StyleApplyResponse(
            success=True,
            original_code=request.code,
            transformed_code=transformed_code,
            execution_verification=execution_verification,
            summary=summary,
            applied_rules=applied_rules,
            warnings=warnings,
        )
'''


class RouteFinalExecutionTests(unittest.TestCase):
    def run_route(self, profile=SPLIT_PROFILE, old_report=None, final_report=None,
                  old_transformed=None, old_warnings=None, function_cases=None,
                  verifier_exception=False):
        source = V1_INSTALLER.patch_route(ROUTE_BEFORE_V1)
        source = INSTALLER.patch_route(source)
        calls = []
        if final_report is None:
            final_report = check_result()

        def fake_verifier(**kwargs):
            calls.append(kwargs)
            if verifier_exception:
                raise RuntimeError('verifier failed')
            return final_report

        def fake_apply(**kwargs):
            return (old_transformed if old_transformed is not None else SOURCE,
                    '기존 단계에서 최종 코드 변경이 없어 별도의 실행 결과 비교를 수행하지 않았습니다.',
                    ['이전 문법 변환'], list(old_warnings or []), {}, old_report)

        fake_service = types.ModuleType('app.services.style_apply_service')
        fake_service.apply_coding_style = fake_apply
        fake_verify = types.ModuleType('app.services.execution_validation_service')
        fake_verify.verify_execution_equivalence = fake_verifier
        scope = {'StyleApplyResponse': lambda **kwargs: types.SimpleNamespace(**kwargs)}
        modules = {
            'app.services.style_apply_service': fake_service,
            'app.services.execution_validation_service': fake_verify,
        }
        style = types.SimpleNamespace(formatting_style=profile, model_dump=lambda: {'formatting_style': profile})
        request = types.SimpleNamespace(code=SOURCE, style=style, function_cases=function_cases)
        with patch.dict(sys.modules, modules):
            exec(source, scope)
            response = scope['apply_style_api'](request)
        return response, calls, source

    def test_formatting_only_provides_both_stdout(self):
        response, calls, _ = self.run_route()
        self.assertIn('  total = 0\n  count = 0', response.transformed_code)
        self.assertEqual(response.execution_verification['original']['stdout'], '(6, 3)\n')
        self.assertEqual(response.execution_verification['transformed']['stdout'], '(6, 3)\n')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['original_code'], SOURCE)
        self.assertEqual(calls[0]['transformed_code'], response.transformed_code)
        self.assertIn('실행 결과를 비교', response.summary)

    def test_function_cases_sent_to_verifier(self):
        cases = [{'function': 'calculate', 'args': [[1, 2, 3]]}]
        _, calls, _ = self.run_route(function_cases=cases)
        self.assertEqual(calls[0]['function_cases'], cases)

    def test_existing_tag_verdict_refreshed_for_final(self):
        prior = check_result('equivalent')
        response, calls, _ = self.run_route(old_report=prior)
        self.assertEqual(len(calls), 1)
        self.assertEqual(response.execution_verification, check_result())

    def test_legacy_style_no_extra_verification(self):
        response, calls, _ = self.run_route(profile=None)
        self.assertEqual(response.transformed_code, SOURCE)
        self.assertEqual(calls, [])
        self.assertIsNone(response.execution_verification)

    def test_existing_rollback_prevents_formatting(self):
        response, calls, _ = self.run_route(old_report={'status': 'different', 'equivalent': False})
        self.assertEqual(response.transformed_code, SOURCE)
        self.assertEqual(calls, [])

    def test_formatting_runtime_mismatch_cancels_only_formatting(self):
        response, calls, _ = self.run_route(final_report=check_result('different'))
        self.assertEqual(response.transformed_code, SOURCE)
        self.assertEqual(response.applied_rules, ['이전 문법 변환'])
        self.assertTrue(any('서식 변경을 취소' in s for s in response.warnings))
        self.assertEqual(len(calls), 1)

    def test_mismatch_keeps_previous_semantic_verdict(self):
        prior = check_result('equivalent')
        response, _, _ = self.run_route(old_report=prior, final_report=check_result('different'))
        self.assertIs(response.execution_verification, prior)

    def test_verifier_exception_cancels_format(self):
        response, _, _ = self.run_route(verifier_exception=True)
        self.assertEqual(response.transformed_code, SOURCE)
        self.assertEqual(response.applied_rules, ['이전 문법 변환'])
        self.assertTrue(any('실행 검증기' in s for s in response.warnings))

    def test_malformed_verifier_no_outputs_cancels_format(self):
        response, _, _ = self.run_route(final_report={'status': 'equivalent', 'equivalent': True})
        self.assertEqual(response.transformed_code, SOURCE)
        self.assertIsNone(response.execution_verification)

    def test_not_verified_shows_blocked_results(self):
        report = check_result('not_verified')
        report['original']['blocked'] = True
        report['original']['block_reason'] = 'blocked sample'
        response, _, _ = self.run_route(final_report=report)
        self.assertEqual(response.execution_verification['status'], 'not_verified')
        self.assertEqual(response.execution_verification['original']['block_reason'], 'blocked sample')
        self.assertTrue(any('동등성' in s for s in response.warnings))

    def test_rule_still_reported_after_pass(self):
        response, _, _ = self.run_route()
        self.assertTrue(any('들여쓰기' in r or '줄바꿈' in r for r in response.applied_rules))

    def test_no_rewrite_of_unrelated_code(self):
        _, _, source = self.run_route()
        self.assertEqual(source.count(INSTALLER.V2), 2)
        self.assertEqual(source.count('def apply_style_api('), 1)
        ast.parse(source)


class InstallerTests(unittest.TestCase):
    def test_requires_v1(self):
        with self.assertRaises(INSTALLER.InstallationError):
            INSTALLER.patch_route(ROUTE_BEFORE_V1)

    def test_idempotent(self):
        source = V1_INSTALLER.patch_route(ROUTE_BEFORE_V1)
        new = INSTALLER.patch_route(source)
        self.assertEqual(INSTALLER.patch_route(new), new)

    def test_missing_anchor_fails(self):
        source = V1_INSTALLER.patch_route(ROUTE_BEFORE_V1)
        with self.assertRaises(INSTALLER.InstallationError):
            INSTALLER.patch_route(source.replace('        formatting_profile = request.style.formatting_style', '        formatting_profile = None'))

    def test_bom_and_crlf_survive(self):
        source = V1_INSTALLER.patch_route(ROUTE_BEFORE_V1).replace('\n', '\r\n')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'backend/app/api/routes/style_apply.py'
            target.parent.mkdir(parents=True)
            target.write_bytes(b'\xef\xbb\xbf' + source.encode('utf-8'))
            changes = INSTALLER.plan(root)
            self.assertIsNotNone(changes)
            self.assertTrue(changes[2].startswith(b'\xef\xbb\xbf'))
            self.assertIn(b'\r\n', changes[2])

    def test_install_writes_backup_and_does_not_overwrite(self):
        source = V1_INSTALLER.patch_route(ROUTE_BEFORE_V1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'backend/app/api/routes/style_apply.py'
            target.parent.mkdir(parents=True)
            target.write_text(source, encoding='utf-8')
            backup_root = root / 'backup'
            out = INSTALLER.install(root, backup_root)
            self.assertIn('수정 완료', out)
            self.assertTrue((backup_root / 'backend/app/api/routes/style_apply.py').is_file())
            self.assertIn(INSTALLER.V2, target.read_text(encoding='utf-8'))
            self.assertIn('이미', INSTALLER.install(root, backup_root))

    def test_non_utf8_fails_without_change(self):
        source = V1_INSTALLER.patch_route(ROUTE_BEFORE_V1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'backend/app/api/routes/style_apply.py'
            target.parent.mkdir(parents=True)
            bad = source.encode('cp949') + b'\xff'
            target.write_bytes(bad)
            with self.assertRaises(INSTALLER.InstallationError):
                INSTALLER.plan(root)
            self.assertEqual(target.read_bytes(), bad)


if __name__ == '__main__':
    unittest.main()
