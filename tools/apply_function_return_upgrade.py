"""Upgrade function-return result display without rewriting unrelated capstone features.

Run from the capstone_main repository root:
    python tools/apply_function_return_upgrade.py

The script validates every edit before writing any file, backs up each changed
source, then writes complete replacement files with their existing contents
preserved outside the intended changes. It does not change existing storage,
login, sharing, tag analysis, or transformation functions.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent


class PatchError(RuntimeError):
    pass


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one matching code block, found {count}. No files were changed.")
    return source.replace(old, new, 1)


def patch_function_service(source: str) -> str:
    source = replace_once(
        source,
        '        "message": "",\n    }\n\n    if original.blocked or transformed.blocked:',
        '        "message": "",\n'
        '        "original_result": None,\n'
        '        "transformed_result": None,\n'
        '        "original_stdout": None,\n'
        '        "transformed_stdout": None,\n'
        '    }\n\n    if original.blocked or transformed.blocked:',
        'function result default fields',
    )
    source = replace_once(
        source,
        '    before_stdout, before_record = before\n'
        '    after_stdout, after_record = after\n',
        '    before_stdout, before_record = before\n'
        '    after_stdout, after_record = after\n'
        '\n'
        '    # Display the actual observations for the supplied function arguments.\n'
        '    # Preserve type information (list vs tuple, int vs bool, None, etc.).\n'
        '    item["original_result"] = before_record\n'
        '    item["transformed_result"] = after_record\n'
        '    item["original_stdout"] = before_stdout\n'
        '    item["transformed_stdout"] = after_stdout\n',
        'function result record extraction',
    )
    return source


def patch_style_schema(source: str) -> str:
    start = source.find('class FunctionCaseVerification(BaseModel):')
    end = source.find('class FunctionVerification(BaseModel):', start)
    if start < 0 or end < 0:
        raise PatchError('backend function case schema not found')
    part = source[start:end]
    part = replace_once(
        part,
        '    message: str = ""\n',
        '    message: str = ""\n'
        '\n'
        '    # Observed records returned by the function-test harness.\n'
        '    # None means execution was blocked or a result was unavailable.\n'
        '    original_result: Optional[Dict[str, Any]] = None\n'
        '    transformed_result: Optional[Dict[str, Any]] = None\n'
        '    original_stdout: Optional[str] = None\n'
        '    transformed_stdout: Optional[str] = None\n',
        'backend function case schema fields',
    )
    return source[:start] + part + source[end:]


def patch_frontend_types(source: str) -> str:
    old = 'export type FunctionCaseVerification = {'
    insert = '''export type FunctionResultRecord = {
  kind: "value" | "exception" | "unsupported";
  value?: unknown;
  type?: string;
  message?: string;
  reason?: string;
};

'''
    source = replace_once(source, old, insert + old, 'frontend return record type')
    start = source.find('export type FunctionCaseVerification = {')
    end = source.find('export type FunctionVerification = {', start)
    if start < 0 or end < 0:
        raise PatchError('frontend function test result type not found')
    part = source[start:end]
    part = replace_once(
        part,
        '  message: string;\n',
        '  message: string;\n'
        '  original_result?: FunctionResultRecord | null;\n'
        '  transformed_result?: FunctionResultRecord | null;\n'
        '  original_stdout?: string | null;\n'
        '  transformed_stdout?: string | null;\n',
        'frontend function test result fields',
    )
    return source[:start] + part + source[end:]


def patch_style_application(source: str) -> str:
    source = replace_once(
        source,
        '    # 4. 실제 코드 변경이 발생한 경우 실행 결과를 검증합니다.\n'
        '    if _is_changed(code, transformed_code):',
        '    # 4. 코드가 변경되었거나 명시적 함수 테스트가 요청되면 검증합니다.\n'
        '    #    변환이 일어나지 않아도 입력 인자에 따른 반환값을 확인할 수 있습니다.\n'
        '    if _is_changed(code, transformed_code) or function_cases is not None:',
        'backend function testing trigger',
    )
    return source


def patch_style_apply_section(source: str) -> str:
    source = replace_once(
        source,
        'import CodeViewer from "../editor/CodeViewer";',
        'import CodeViewer from "../editor/CodeViewer";\n'
        'import FunctionReturnResults from "./FunctionReturnResults";',
        'frontend return result component import',
    )
    start_marker = '            {functionVerification && ('
    stop_marker = '            {/* 변환 상세 정보 */}'
    start = source.find(start_marker)
    end = source.find(stop_marker, start)
    if start < 0 or end < 0 or start >= end:
        raise PatchError('Cannot find the frontend function result block. No files were changed.')

    # Preserve the heading comment directly above the next section.
    separator = '            {/* ========================================= */}\n'
    pos = source.rfind(separator, start, end)
    if pos < 0:
        raise PatchError('Cannot locate frontend section boundary safely.')

    new_block = '''            {functionVerification && (
              <FunctionReturnResults verification={functionVerification} />
            )}

            {!functionVerification && useFunctionTests && styleApplyResult && (
              <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 p-4">
                <p className="text-sm font-semibold text-amber-800">
                  함수 테스트 결과를 확인할 수 없습니다.
                </p>
                <p className="mt-2 text-sm leading-relaxed text-amber-700">
                  {executionVerification?.message ||
                    "실행 정책 또는 코드 오류로 함수 테스트가 수행되지 않았습니다."}
                </p>
              </div>
            )}

'''
    return source[:start] + new_block + source[pos:]


PATCHES = [
    ('backend/app/services/function_result_validation_service.py', patch_function_service),
    ('backend/app/schemas/style_apply.py', patch_style_schema),
    ('frontend/types/analysis.ts', patch_frontend_types),
    ('backend/app/services/style_apply_service.py', patch_style_application),
    ('frontend/components/sections/StyleApplySection.tsx', patch_style_apply_section),
]


def main() -> int:
    component = ROOT / 'frontend/components/sections/FunctionReturnResults.tsx'
    if not component.is_file():
        raise PatchError('FunctionReturnResults.tsx was not found. Extract the whole ZIP to capstone_main first.')

    outputs: list[tuple[Path, str, str]] = []
    for relative_path, transform in PATCHES:
        source_path = ROOT / relative_path
        if not source_path.is_file():
            raise PatchError(f'Missing source file: {relative_path}')
        original = source_path.read_text(encoding='utf-8')
        updated = transform(original)
        if updated == original:
            raise PatchError(f'No changes generated for: {relative_path}')
        outputs.append((source_path, original, updated))

    # Keep backups OUTSIDE the Git repository to avoid accidentally committing them.
    backup_root = ROOT.parent / 'capstone_function_return_backup'
    for source_path, original, _ in outputs:
        backup = backup_root / source_path.relative_to(ROOT)
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_text(original, encoding='utf-8')

    for source_path, _, updated in outputs:
        source_path.write_text(updated, encoding='utf-8')
        print('Updated complete file:', source_path.relative_to(ROOT))

    print('Complete. All original source sections not involved in this change were retained.')
    print('Backups are outside the Git repository:', backup_root)
    print('Next: docker compose up -d --build frontend backend')
    print('Then: docker compose exec -T frontend npx tsc --noEmit')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (PatchError, OSError, UnicodeError) as error:
        print(f'Upgrade aborted: {error}', file=sys.stderr)
        sys.exit(1)
