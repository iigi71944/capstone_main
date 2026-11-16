"""Isolated installer checks. Does not change the real repository."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/install_strict_validation_batch16.py'
spec = importlib.util.spec_from_file_location('capstone_batch16_installer_fixture', SCRIPT)
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)


FRAGMENTS = {
    'backend/app/schemas/style_apply.py': '''class Sample:
    function_cases: Optional[List[FunctionTestCase]] = Field(
        default=None,
        min_length=1,
        max_length=8,
    )
''',
    'backend/app/api/routes/style_apply.py': '''def apply_style_api(request):
    function_cases = None
    if True:
        (
            transformed_code,
            summary,
        ) = apply_coding_style(
            code=request.code,
            style=request.style.model_dump(),
            function_cases=function_cases,
        )
        if True:
            if not check_valid:
                # Missing/contradictory verification must not silently count
                pass
        if displayed_code != transformed_code:
            transformed_code = displayed_code
        if True:
            summary = (summary or "") + (
                "dummy"
            ) + (
                " 최종 표시 코드에서 주석과 독립 문자열 설명문을 제외했습니다."
            )

        return StyleApplyResponse(
            success=True,
        )
''',
    'frontend/types/analysis.ts': '  function_cases?: FunctionTestCase[] | null;\n',
    'frontend/lib/api.ts': '''  functionCases?: FunctionTestCase[] | null
): Promise<StyleApplyResponse>
  if (functionCases != null) {
    requestBody.function_cases = functionCases;
  }

  const response = await fetch(
''',
    'frontend/hooks/useStyleApplication.ts': '''  const handleApplyStyle = async (
    functionCases?: FunctionTestCase[] | null
  ) => {
        selectedStyle,
        functionCases
      );
''',
    'frontend/components/sections/StyleApplySection.tsx': '''  handleApplyStyle: (
    functionCases?: FunctionTestCase[] | null
  ) => void | Promise<void>;
  const [useFunctionTests, setUseFunctionTests] =
    useState(false);
      void handleApplyStyle();
    void handleApplyStyle(cases);
          {/* 스타일 적용 버튼 */}
''',
}


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.git').mkdir()
        self.initial = {}
        self.shas = {}
        for path, fragment in FRAGMENTS.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            text = fragment.replace('\n', '\r\n') if 'StyleApplySection' in path else fragment
            if 'style_apply.py' in path and path.startswith('backend/app/schemas/'):
                text = '\ufeff' + text
            target.write_bytes(text.encode('utf-8'))
            self.initial[path] = target.read_bytes()
            self.shas[path] = installer._blob_sha(fragment)
        self.original_shas = installer.BASE_SHA
        installer.BASE_SHA = self.shas
        self.addCleanup(setattr, installer, 'BASE_SHA', self.original_shas)

    def test_check_is_read_only(self):
        result = installer.install(self.root, check=True)
        self.assertIn('9 file changes', result)
        for path, data in self.initial.items():
            self.assertEqual((self.root / path).read_bytes(), data)
        self.assertFalse((self.root / '.git/capstone_batch16_backups').exists())

    def test_install_and_idempotence(self):
        result = installer.install(self.root)
        self.assertIn('installed', result)
        self.assertIn('already_installed', installer.install(self.root, check=True))
        self.assertIn('already_installed', installer.install(self.root))

    def test_all_patched_file_markers(self):
        installer.install(self.root)
        for path in FRAGMENTS:
            self.assertIn(installer.MARK, (self.root / path).read_text(encoding='utf-8-sig'))

    def test_backups_preserve_originals(self):
        installer.install(self.root)
        for path, data in self.initial.items():
            backup = self.root / '.git/capstone_batch16_backups' / path
            self.assertEqual(backup.read_bytes(), data)

    def test_windows_eol_and_bom_preserved(self):
        installer.install(self.root)
        crlf = (self.root / 'frontend/components/sections/StyleApplySection.tsx').read_bytes()
        self.assertIn(b'\r\n',crlf)
        self.assertNotIn(b'\n',crlf.replace(b'\r\n', b''))
        bom = (self.root / 'backend/app/schemas/style_apply.py').read_bytes()
        self.assertTrue(bom.startswith(b'\xef\xbb\xbf'))

    def test_modified_file_blocks_all_writes(self):
        path='frontend/lib/api.ts'
        (self.root / path).write_text('unexpected', encoding='utf-8')
        with self.assertRaises(RuntimeError):
            installer.install(self.root)
        self.assertEqual((self.root / 'backend/app/schemas/style_apply.py').read_bytes(),
                         self.initial['backend/app/schemas/style_apply.py'])

    def test_partial_install_blocks_all_writes(self):
        path='frontend/types/analysis.ts'
        before=(self.root / path).read_text()
        changed=installer.patch(path,before)
        (self.root / path).write_text(changed)
        with self.assertRaises(RuntimeError):
            installer.install(self.root)
        self.assertEqual((self.root / 'frontend/lib/api.ts').read_bytes(),
                         self.initial['frontend/lib/api.ts'])


if __name__ == '__main__':
    unittest.main()
