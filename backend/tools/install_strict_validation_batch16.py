"""Batch 16: install opt-in strict runtime verification across Style Apply.

Version-locked to GitHub main 8a1001e. Read-only --check supported.
Writes backups to .git; never overwrites a modified or unexpected file.
ZIP paths and payload filenames are ASCII for Windows PowerShell.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = Path(__file__).resolve().parent / 'batch16_payload'
MARK = 'CAPSTONE_BATCH16_STRICT_VERIFY_V1'

# Exact base blobs from GitHub revision 8a1001e. EOL normalized for Windows checkout.
BASE_SHA = {
    'backend/app/schemas/style_apply.py': '884f12c5db67e5cb7f676569c771228805d69e55',
    'backend/app/api/routes/style_apply.py': '99d034eb45d176c8bc3a6c6208a567cb27708f6f',
    'frontend/types/analysis.ts': '787c8ae7fc4f687949f068a41a791fc0e0f30a86',
    'frontend/lib/api.ts': '061d3c97e824196104279fc0073d4cdb9800c48e',
    'frontend/hooks/useStyleApplication.ts': 'cc7b7740cb52ab191c049a382423a159d7bdf5a1',
    'frontend/components/sections/StyleApplySection.tsx': 'e7f3e2f743efdb16a1fe5b896178cfe913b5f16f',
}
NEW_FILES = {
    'backend/tests/test_style_strict_validation_batch16.py': 'test_style_strict_validation_batch16.py.source',
    'backend/tools/audit_style_strict_validation_batch16.py': 'audit_style_strict_validation_batch16.py.source',
    'backend/tests/test_style_strict_installer_batch16.py': 'test_style_strict_installer_batch16.py.source',
}


def _blob_sha(normalized_source: str) -> str:
    data = normalized_source.encode('utf-8')
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def _read_source(path: Path) -> tuple[str, str, bool]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b'\xef\xbb\xbf')
    decoded = raw.decode('utf-8-sig' if has_bom else 'utf-8')
    eol = '\r\n' if '\r\n' in decoded else '\n'
    normalized = decoded.replace('\r\n', '\n')
    return normalized, eol, has_bom


def _replace(src: str, before: str, after: str, label: str) -> str:
    count = src.count(before)
    if count != 1:
        raise ValueError(f'{label}: expected exactly one anchor, found {count}')
    return src.replace(before, after, 1)


def patch(path: str, src: str) -> str:
    if path == 'backend/app/schemas/style_apply.py':
        src = _replace(src,
            '    function_cases: Optional[List[FunctionTestCase]] = Field(\n'
            '        default=None,\n        min_length=1,\n        max_length=8,\n    )\n',
            '    function_cases: Optional[List[FunctionTestCase]] = Field(\n'
            '        default=None,\n        min_length=1,\n        max_length=8,\n    )\n'
            f'\n    # {MARK}: opt-in; old clients remain permissive.\n'
            '    strict_runtime_validation: bool = False\n', path)

    elif path == 'backend/app/api/routes/style_apply.py':
        src = _replace(src,
            '        (\n            transformed_code,\n            summary,\n',
            f'        # {MARK}: retain compatibility with older request stubs.\n'
            '        strict_runtime_validation = getattr(request, "strict_runtime_validation", False)\n\n'
            '        (\n            transformed_code,\n            summary,\n',
            path+' flag variable')
        src = _replace(src,
            '        ) = apply_coding_style(\n            code=request.code,\n'
            '            style=request.style.model_dump(),\n'
            '            function_cases=function_cases,\n        )',
            '        ) = apply_coding_style(\n            code=request.code,\n'
            '            style=request.style.model_dump(),\n'
            '            function_cases=function_cases,\n'
            '            strict_runtime_validation=strict_runtime_validation,\n        )', path+' pass-through')
        src = _replace(src,
            '            if not check_valid:\n                # Missing/contradictory verification must not silently count',
            f'            # {MARK}: strict mode also rejects uncertain formatting.\n'
            '            if (check_valid and strict_runtime_validation\n'
            '                    and final_check["status"] == "not_verified"):\n'
            '                check_valid = False\n\n'
            '            if not check_valid:\n                # Missing/contradictory verification must not silently count',
            path+' formatting')
        src = _replace(src,
            '        if displayed_code != transformed_code:\n            transformed_code = displayed_code\n',
            '        if displayed_code != transformed_code:\n'
            '            # Before cleanup: preserve the exact prior verified source.\n'
            '            code_before_cleanup = transformed_code\n'
            '            verification_before_cleanup = execution_verification\n'
            '            transformed_code = displayed_code\n',
            path+' cleanup snapshot')
        src = _replace(src,
            '            ) + (\n'
            '                " 최종 표시 코드에서 주석과 독립 문자열 설명문을 제외했습니다."\n'
            '            )\n\n        return StyleApplyResponse(',
            '            ) + (\n'
            '                " 최종 표시 코드에서 주석과 독립 문자열 설명문을 제외했습니다."\n'
            '            )\n'
            f'            # {MARK}: never return unverified cleanup in strict mode.\n'
            '            if strict_runtime_validation and (\n'
            '                not cleanup_valid or cleanup_check["status"] != "equivalent"\n'
            '            ):\n'
            '                transformed_code = code_before_cleanup\n'
            '                execution_verification = verification_before_cleanup\n'
            '                summary = summary.replace(\n'
            '                    " 최종 표시 코드에서 주석과 독립 문자열 설명문을 제외했습니다.",\n'
            '                    " 엄격 검증 설정에 따라 주석·독립 문자열 제거를 취소했습니다.",\n'
            '                )\n'
            '                warnings.append(\n'
            '                    "엄격 실행 검증: 주석·독립 문자열 제거의 실행 동등성이 "\n'
            '                    "확인되지 않아 해당 변경을 취소했습니다."\n'
            '                )\n\n        return StyleApplyResponse(',
            path+' cleanup guard')

    elif path == 'frontend/types/analysis.ts':
        src = _replace(src,
            '  function_cases?: FunctionTestCase[] | null;\n',
            '  function_cases?: FunctionTestCase[] | null;\n'
            f'  // {MARK}: optional for backward compatibility.\n'
            '  strict_runtime_validation?: boolean;\n', path)

    elif path == 'frontend/lib/api.ts':
        src = _replace(src,
            '  functionCases?: FunctionTestCase[] | null\n): Promise<StyleApplyResponse>',
            '  functionCases?: FunctionTestCase[] | null,\n'
            '  strictRuntimeValidation: boolean = false\n): Promise<StyleApplyResponse>', path+' arguments')
        src = _replace(src,
            '  if (functionCases != null) {\n    requestBody.function_cases = functionCases;\n  }\n\n  const response = await fetch(',
            '  if (functionCases != null) {\n    requestBody.function_cases = functionCases;\n  }\n'
            f'\n  // {MARK}: omit the field for existing clients.\n'
            '  if (strictRuntimeValidation) {\n'
            '    requestBody.strict_runtime_validation = true;\n'
            '  }\n\n  const response = await fetch(', path+' request')

    elif path == 'frontend/hooks/useStyleApplication.ts':
        src = _replace(src,
            '  const handleApplyStyle = async (\n    functionCases?: FunctionTestCase[] | null\n  ) => {',
            f'  // {MARK}: forward the opt-in to API.\n'
            '  const handleApplyStyle = async (\n    functionCases?: FunctionTestCase[] | null,\n'
            '    strictRuntimeValidation: boolean = false\n  ) => {',
            path+' arguments')
        src = _replace(src,
            '        selectedStyle,\n        functionCases\n      );',
            '        selectedStyle,\n        functionCases,\n'
            '        strictRuntimeValidation\n      );', path+' dispatch')

    elif path == 'frontend/components/sections/StyleApplySection.tsx':
        src = _replace(src,
            '  handleApplyStyle: (\n    functionCases?: FunctionTestCase[] | null\n  ) => void | Promise<void>;',
            '  handleApplyStyle: (\n    functionCases?: FunctionTestCase[] | null,\n'
            '    strictRuntimeValidation?: boolean\n  ) => void | Promise<void>;', path+' props')
        src = _replace(src,
            '  const [useFunctionTests, setUseFunctionTests] =\n    useState(false);',
            '  const [useFunctionTests, setUseFunctionTests] =\n    useState(false);\n'
            f'\n  // {MARK}: strict verification is opt-in.\n'
            '  const [strictRuntimeValidation, setStrictRuntimeValidation] = useState(false);',
            path+' state')
        src = _replace(src,
            '      void handleApplyStyle();',
            '      void handleApplyStyle(undefined, strictRuntimeValidation);',
            path+' no function cases')
        src = _replace(src,
            '    void handleApplyStyle(cases);',
            '    void handleApplyStyle(cases, strictRuntimeValidation);',
            path+' function cases')
        src = _replace(src,
            '          {/* 스타일 적용 버튼 */}',
            f'          {{/* {MARK}: optional rollback of unverified results */}}\n'
            '          <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4">\n'
            '            <label className="flex cursor-pointer items-center gap-3">\n'
            '              <input\n'
            '                type="checkbox"\n'
            '                checked={strictRuntimeValidation}\n'
            '                onChange={(event) => {\n'
            '                  setStrictRuntimeValidation(event.target.checked);\n'
            '                  clearPreviousResult();\n'
            '                }}\n'
            '                disabled={styleApplyLoading}\n'
            '                className="h-4 w-4 accent-slate-900"\n'
            '              />\n'
            '              <span className="text-sm font-semibold text-slate-800">\n'
            '                엄격 실행 검증 (검증 불가 시 변경 취소)\n'
            '              </span>\n'
            '            </label>\n'
            '            <p className="mt-2 text-xs leading-relaxed text-slate-600">\n'
            '              선택하면 실행 결과가 다르거나 동등성을 검증할 수 없는\n'
            '              문법·개념 변환, 서식 변경, 주석 정리를 취소합니다.\n'
            '              선택하지 않으면 기존 처리 방식을 유지합니다.\n'
            '              검사하지 않은 모든 입력의 동등성을 보장하지는 않습니다.\n'
            '            </p>\n'
            '          </div>\n\n'
            '          {/* 스타일 적용 버튼 */}', path+' UI')
    else:
        raise ValueError('Unexpected patch path: ' + path)
    return src


def _encoded(source: str, eol: str, bom: bool) -> bytes:
    result = source.replace('\n', eol).encode('utf-8')
    return (b'\xef\xbb\xbf' if bom else b'') + result


def build_changes(root: Path = ROOT) -> tuple[dict[Path, bytes], str]:
    changes: dict[Path, bytes] = {}
    state = []
    for relative, sha in BASE_SHA.items():
        file = root / relative
        if not file.is_file():
            raise RuntimeError(f'Missing tracked file: {relative}')
        source, eol, bom = _read_source(file)
        already = MARK in source
        state.append(already)
        if already:
            continue
        if _blob_sha(source) != sha:
            raise RuntimeError(f'Unexpected file version; do not overwrite: {relative}')
        updated = patch(relative, source)
        if updated == source:
            raise RuntimeError('Patch made no changes: ' + relative)
        if relative.endswith('.py'):
            ast.parse(updated, filename=relative)
        changes[file] = _encoded(updated, eol, bom)

    for relative, payload_name in NEW_FILES.items():
        destination = root / relative
        payload = PAYLOAD / payload_name
        if not payload.is_file():
            raise RuntimeError('Missing ZIP payload: ' + payload_name)
        data = payload.read_bytes()
        if destination.exists():
            if destination.read_bytes() != data:
                raise RuntimeError('Unexpected existing file: ' + relative)
        else:
            changes[destination] = data

    if all(state) and all((root / p).is_file() for p in NEW_FILES):
        if changes:
            raise RuntimeError('Installed marker found but files incomplete')
        return {}, 'already_installed'
    if any(state):
        raise RuntimeError('Partial prior installation detected; no files changed')
    return changes, 'ready'


def install(root: Path = ROOT, check: bool = False) -> str:
    changes, status = build_changes(root)
    if check or status == 'already_installed':
        return f'{status}: {len(changes)} file changes planned'

    git_dir = root / '.git'
    if not git_dir.is_dir():
        raise RuntimeError('Expected existing .git folder before installation')
    backup_dir = git_dir / 'capstone_batch16_backups'
    if backup_dir.exists():
        raise RuntimeError('Backup directory exists; inspect prior installation')
    backup_dir.mkdir(parents=True)
    saved = {}
    try:
        for path in changes:
            if path.is_file():
                old = path.read_bytes()
                saved[path] = old
                backup_path = backup_dir / path.relative_to(root)
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                backup_path.write_bytes(old)
        for path, data in changes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix='.batch16-')
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(data)
                os.replace(tmp_name, path)
            finally:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
    except Exception:
        for path in changes:
            if path in saved:
                path.write_bytes(saved[path])
            elif path.exists():
                path.unlink()
        raise
    return f'installed: {len(changes)} file changes, backups: {backup_dir}'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(install(check=args.check))
        return 0
    except (OSError, RuntimeError, ValueError, UnicodeError, SyntaxError) as error:
        print(f'Batch16 installation stopped: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
