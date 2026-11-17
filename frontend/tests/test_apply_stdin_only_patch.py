import importlib.util
import unittest
from pathlib import Path

FILE = Path(__file__).resolve().parents[1] / 'tools' / 'apply_stdin_only_fix.py'
spec = importlib.util.spec_from_file_location('stdinfix', FILE)
fix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fix)

OLD_MIDDLE = '''  const parseFunctionCases = ():
    | FunctionTestCase[]
    | null => {
    const cases: FunctionTestCase[] = [];
    const functionName = draft.functionName.trim();
    if (!functionName) {
      return null;
    }
    return cases;
  };
  const submitStyleApplication = () => {
    void handleApplyStyle(cases, false, undefined);
  };

'''

OLD_LABELS = ('''                  함수 반환값 검증
'''
              '''                  함수 검증 사용
'''
              '''                  함수에 같은 값을 넣어 실행한 뒤,
'''
              '''                  스타일 적용 전후의 결과가 같은지
'''
              '''                  확인합니다.
'''
              '''                    코드에 작성된 함수 이름과
'''
              '''                    함수에 넣을 값을 입력해주세요.
'''
              '''                    값을 넣는 방식은 두 가지이며,
'''
              '''                    필요한 방식만 사용하시면 됩니다.
'''
              '''                            코드에 정의된 함수 이름을
'''
              '''                            그대로 입력해주세요.
'''
              '''                            이 함수 테스트의 사용자 입력값 (stdin) ''')

SOURCE = fix.IMPORT_FROM + OLD_MIDDLE + fix.END + OLD_LABELS

class PatchTests(unittest.TestCase):
    def test_apply_and_idempotent(self):
        updated, status = fix.patch_source(SOURCE)
        self.assertEqual(status, 'ready')
        self.assertIn(fix.MARKER, updated)
        self.assertIn('parseVerificationInputs(functionDrafts)', updated)
        self.assertIn('void handleApplyStyle(selected.functionCases, false, selected.stdin)', updated)
        self.assertNotIn('const parseFunctionCases', updated)
        self.assertEqual(fix.patch_source(updated), (updated, 'already_applied'))

    def test_crlf(self):
        src = SOURCE.replace('\n', '\r\n')
        updated, status = fix.patch_source(src)
        self.assertEqual(status,'ready')
        self.assertEqual(updated.count('\r\n'),updated.count('\n'))
        self.assertEqual(fix.patch_source(updated),(updated,'already_applied'))

    def test_refuse_old_version(self):
        with self.assertRaises(ValueError):
            fix.patch_source(SOURCE.replace('const cases: FunctionTestCase[] = [];','const wrong = [];'))

    def test_refuse_missing_anchor(self):
        with self.assertRaises(ValueError):
            fix.patch_source(SOURCE.replace(fix.START, '  wrong()=>{\n'))

    def test_refuse_modified_ui_text(self):
        with self.assertRaises(ValueError):
            fix.patch_source(SOURCE.replace('                  함수 검증 사용\n', '                  different\n'))

    def test_reject_mixed_newlines(self):
        with self.assertRaises(ValueError):
            fix.patch_source(SOURCE.replace('\n','\r\n',1))

if __name__ == '__main__':
    unittest.main()
