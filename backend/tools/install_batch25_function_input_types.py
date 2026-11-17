"""Batch 25: remove input placeholders and enforce supported function input types.

Baseline: GitHub main f559b62 (Batch24). Run from capstone_main root:
  python backend/tools/install_batch25_function_input_types.py --check
  python backend/tools/install_batch25_function_input_types.py

Preflight detects changed files before any write. Each original is backed up
under .git/capstone_batch25_backups and writes are rolled back on failure.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = Path('backend/tools/batch25_payload')
MARK = 'CAPSTONE_BATCH25_'
BASE = {
    Path('frontend/components/sections/StyleApplySection.tsx'):
        'a24cfc1f128cb19964aa8c1817b82b2c9efb91a9',
    Path('backend/app/services/function_result_validation_service.py'):
        '589608f2cd621abf5cf97c50dab5c94ba6c2c945',
    Path('backend/app/api/routes/style_apply.py'):
        '84ed9aec80f7ba149d2939d81e092a627791a8c9',
}
NEW = {
    Path('backend/app/services/function_input_type_guard_service.py'):
        PAYLOAD / 'function_input_type_guard_service.py.source',
    Path('backend/tests/test_function_input_type_guard_batch25.py'):
        PAYLOAD / 'test_function_input_type_guard_batch25.py.source',
}


def once(text: str, before: str, after: str, label: str) -> str:
    if text.count(before) != 1:
        raise RuntimeError(f'{label}: expected one exact insertion point, found {text.count(before)}')
    return text.replace(before, after, 1)


def patch_ui(source: str) -> str:
    if MARK in source:
        raise RuntimeError('Batch25 UI already changed outside installer')
    source = once(source,
        '                            placeholder="greet"\n',
        '',
        'Function name placeholder')
    source = once(source,
        '                        {/* 함수 이름 */}',
        '                        {/* 함수 이름 · CAPSTONE_BATCH25_CLEAR_NAME_PLACEHOLDER_V1 */}',
        'Function name marker')
    source = once(source,
        '                            placeholder={"5\\n10"}\n',
        '',
        'Stdin placeholder')
    source = once(source,
        '                        {/* 사용자 입력값: 이 함수 테스트에만 적용하는 override */}',
        '                        {/* 사용자 입력값: 이 함수 테스트에만 적용 · CAPSTONE_BATCH25_CLEAR_STDIN_PLACEHOLDER_V1 */}',
        'Stdin marker')
    source = once(source,
        '                            입력 예: 5 (한 번), 5와 10 (두 줄). 대괄호 없이 각 줄에 입력합니다.\n',
        '                            {/* CAPSTONE_BATCH25_TYPE_NOTICE_V1 */}\n'
        '                            각 입력값은 코드에서 요구하는 자료형에 맞아야 합니다.\n'
        '                            input()은 문자열을 반환하며, int(input())는 정수로,\n'
        '                            float(input())는 실수로 변환 가능한 값을 입력해야 합니다.\n'
        '                            대괄호 없이 입력 순서대로 한 줄에 한 값씩 작성해주세요.\n',
        'Stdin type notice')
    source = once(source,
        '                      함수에 값을 차례대로 전달합니다.\n',
        '                      함수의 위치 인자를 왼쪽부터 순서대로 전달합니다.\n'
        '                      리스트 한 개를 전달할 때는 [[1, 2, 3]]처럼 작성합니다.\n',
        'Positional args explanation')
    source = once(source,
        '                            입력합니다. 사용하지 않으면\n                            []로 두세요.\n',
        '                            입력합니다. 타입 힌트나 기본값이 있는\n'
        '                            매개변수는 해당 자료형과 일치해야 합니다.\n'
        '                            사용하지 않으면 []로 두세요.\n',
        'Function argument type note')
    return source


def patch_validation(source: str) -> str:
    source = once(source,
        'from app.services.execution_validation_service import (\n',
        '# CAPSTONE_BATCH25_FUNCTION_TYPE_GUARD_IMPORT_V1\n'
        'from app.services.function_input_type_guard_service import validate_function_test_case\n\n'
        'from app.services.execution_validation_service import (\n',
        'Guard import')
    source = once(source,
        '    # Validate all test inputs before executing any supplied code.\n'
        '    for case in cases:\n'
        '        _validated_case(case)\n',
        '    # CAPSTONE_BATCH25_FUNCTION_TYPE_GUARD_V1: reject known mismatches\n'
        '    # before any user code is executed in the test runner.\n'
        '    for case in cases:\n'
        '        _validated_case(case)\n'
        '        validate_function_test_case(original_code, case, stdin=stdin)\n'
        '        if transformed_code != original_code:\n'
        '            validate_function_test_case(transformed_code, case, stdin=stdin)\n',
        'Verifier preflight')
    ast.parse(source)
    return source


def patch_route(source: str) -> str:
    source = once(source,
        'from app.services.style_apply_service import apply_coding_style\n',
        '# CAPSTONE_BATCH25_ROUTE_GUARD_IMPORT_V1\n'
        'from app.services.function_input_type_guard_service import validate_function_test_case\n'
        'from app.services.style_apply_service import apply_coding_style\n',
        'Route import')
    source = once(source,
        '        stdin_input = getattr(request, "stdin", None)\n',
        '        stdin_input = getattr(request, "stdin", None)\n'
        '        # CAPSTONE_BATCH25_ROUTE_INPUT_PRECHECK_V1: show useful errors\n'
        '        # instead of treating matching exceptions as successful verification.\n'
        '        if function_cases is not None:\n'
        '            for case in function_cases:\n'
        '                validate_function_test_case(request.code, case, stdin=stdin_input)\n',
        'Route preflight')
    ast.parse(source)
    return source

PATCHES = {
    Path('frontend/components/sections/StyleApplySection.tsx'): patch_ui,
    Path('backend/app/services/function_result_validation_service.py'): patch_validation,
    Path('backend/app/api/routes/style_apply.py'): patch_route,
}


def sha(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\x00' + data).hexdigest()


def source_file(path: Path):
    original = path.read_bytes()
    bom = original.startswith(b'\xef\xbb\xbf')
    body = original[3:] if bom else original
    if b'\r\n' in body and b'\n' in body.replace(b'\r\n', b''):
        raise RuntimeError(f'Mixed line endings in {path}')
    eol = '\r\n' if b'\r\n' in body else '\n'
    normalized = body.replace(b'\r\n', b'\n')
    return normalized.decode('utf-8'), normalized, original, eol, bom


def encode(content: str, eol: str, bom: bool) -> bytes:
    return (b'\xef\xbb\xbf' if bom else b'') + content.replace('\n', eol).encode('utf-8')


def prepare(root: Path):
    if not (root / '.git').is_dir():
        raise RuntimeError('Run from the capstone_main Git repository root')
    staged, originals = {}, {}
    flags = []
    for rel, patcher in PATCHES.items():
        path = root / rel
        if not path.is_file():
            raise RuntimeError(f'Baseline file not found: {rel}')
        content, normalized, original, eol, bom = source_file(path)
        installed = MARK in content
        flags.append(installed)
        if installed:
            for marker in ('CAPSTONE_BATCH25_CLEAR_NAME_PLACEHOLDER_V1',
                           'CAPSTONE_BATCH25_CLEAR_STDIN_PLACEHOLDER_V1',
                           'CAPSTONE_BATCH25_TYPE_NOTICE_V1') if rel.suffix == '.tsx' else (
                           ('CAPSTONE_BATCH25_FUNCTION_TYPE_GUARD_V1',)
                           if rel.name == 'function_result_validation_service.py'
                           else ('CAPSTONE_BATCH25_ROUTE_INPUT_PRECHECK_V1',)):
                if marker not in content:
                    raise RuntimeError(f'Partial Batch25 changes: missing {marker} in {rel}')
            continue
        if sha(normalized) != BASE[rel]:
            raise RuntimeError(f'Unexpected local edits to {rel}; nothing modified. '
                               'Commit or restore baseline before installing.')
        modified = patcher(content)
        staged[rel] = encode(modified, eol, bom)
        originals[rel] = original
    exists = []
    for rel, payload in NEW.items():
        src = root / payload
        if not src.is_file():
            raise RuntimeError(f'Missing installer payload: {payload}')
        data = src.read_bytes()
        ast.parse(data.decode('utf-8'))
        dest = root / rel
        exists.append(dest.exists())
        if dest.exists():
            if not dest.is_file() or dest.read_bytes() != data:
                raise RuntimeError(f'Existing target differs from Batch25 payload: {rel}')
        else:
            staged[rel] = data
    if (any(flags) or any(exists)) and not (all(flags) and all(exists)):
        raise RuntimeError('Partially installed Batch25; nothing was modified')
    return staged, originals


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.capstone_b25_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def install(root: Path, check: bool = False) -> str:
    staged, originals = prepare(root)
    if not staged:
        return 'Batch25 already installed; no changes.'
    if check:
        return f'Batch25 preflight passed: {len(staged)} files; no files modified.'
    backups = root / '.git' / 'capstone_batch25_backups'
    for rel, content in originals.items():
        destination = backups / rel
        if destination.exists():
            if destination.read_bytes() != content:
                raise RuntimeError(f'Unexpected previous backup: {rel}')
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Backups are created before working files are changed.
            atomic_write(destination, content)
    written = []
    try:
        for rel, payload in staged.items():
            atomic_write(root / rel, payload)
            written.append(rel)
    except Exception:
        for rel in reversed(written):
            if rel in originals:
                atomic_write(root / rel, originals[rel])
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    return f'Installed Batch25: {len(staged)} files; placeholders cleared, type checks added.'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(install(ROOT, check=args.check))
        return 0
    except (OSError, UnicodeError, RuntimeError, SyntaxError, ValueError) as exc:
        print(f'Batch25 installation stopped: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
