"""Regression tests for stdin-only notice condition, without external deps."""
import importlib.util
from pathlib import Path
import unittest

PATCH_PATH = Path(__file__).resolve().parents[1] / 'tools' / 'fix_stdin_only_notice.py'
spec = importlib.util.spec_from_file_location('stdin_only_notice_hotfix', PATCH_PATH)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)

BASE = '''// CAPSTONE_STDIN_ONLY_INDEPENDENT_FUNCTION_CASES_V1
import { parseVerificationInputs } from "../../lib/verificationInputSelection";
function SomeComponent() {
  return <div>
            {!functionVerification && useFunctionTests && styleApplyResult && (
              <div>함수 테스트 결과를 확인할 수 없습니다.</div>
            )}
  </div>;
}
'''


class NoticeHotfixTests(unittest.TestCase):
    def test_converts_exactly_one_condition(self):
        output, state = patch.patch_source(BASE)
        self.assertEqual(state, 'ready')
        self.assertEqual(output.count('functionDrafts.some('), 1)
        self.assertNotIn(patch.OLD, output)
        self.assertIn('함수 테스트 결과를 확인할 수 없습니다.', output)

    def test_only_condition_changes(self):
        output, _ = patch.patch_source(BASE)
        self.assertEqual(output, BASE.replace(patch.OLD, patch.NEW, 1))

    def test_is_idempotent(self):
        output, _ = patch.patch_source(BASE)
        second, status = patch.patch_source(output)
        self.assertEqual(status, 'already_applied')
        self.assertEqual(output, second)

    def test_supports_crlf(self):
        value = BASE.replace('\n', '\r\n')
        output, state = patch.patch_source(value)
        self.assertEqual(state, 'ready')
        self.assertEqual(output.count('\r\n'), output.count('\n'))

    def test_blocks_mixed_line_endings(self):
        value = BASE.replace('\n', '\r\n', 1)
        with self.assertRaisesRegex(ValueError, '혼합'):
            patch.patch_source(value)

    def test_blocks_missing_previous_patch(self):
        with self.assertRaisesRegex(ValueError, '이전 stdin'):
            patch.patch_source(BASE.replace(patch.PREVIOUS_PATCH_MARKER, 'missing'))

    def test_blocks_missing_previous_import(self):
        with self.assertRaisesRegex(ValueError, 'import'):
            patch.patch_source(BASE.replace('import { parseVerificationInputs } from "../../lib/verificationInputSelection";', '// removed'))

    def test_blocks_changed_ui_marker(self):
        with self.assertRaisesRegex(ValueError, '안내 구성'):
            patch.patch_source(BASE.replace('함수 테스트 결과를 확인할 수 없습니다.', 'unrelated'))

    def test_blocks_ambiguous_conditions(self):
        with self.assertRaisesRegex(ValueError, '한 번'):
            patch.patch_source(BASE.replace(patch.OLD, patch.OLD + '\n' + patch.OLD))

    def test_blocks_partially_applied_patch(self):
        output, _ = patch.patch_source(BASE)
        with self.assertRaisesRegex(ValueError, '부분 적용'):
            patch.patch_source(output.replace('functionDrafts.some(', 'BROKEN('))

    def test_keeps_expected_warning_for_actual_requested_function(self):
        output, _ = patch.patch_source(BASE)
        self.assertIn('functionName.trim() !== ""', output)
        self.assertIn('!functionVerification', output)
        self.assertIn('useFunctionTests', output)


if __name__ == '__main__':
    unittest.main()
