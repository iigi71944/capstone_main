"""Batch 18: remove redundant shared-stdin UI, retain per-function stdin.

This installer updates one frontend component from Batch 17, and does not
alter API/backend stdin support. Run from repository root:
  python backend/tools/install_case_stdin_only_batch18.py --check
  python backend/tools/install_case_stdin_only_batch18.py
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile

# Installed at <repo>/backend/tools/<script>.py; parents[2] is <repo>.
ROOT = Path(__file__).resolve().parents[2]
TARGET = Path('frontend/components/sections/StyleApplySection.tsx')
MARK = 'CAPSTONE_BATCH18_CASE_STDIN_ONLY_V1'

OLD_STATE = (
    '  // CAPSTONE_BATCH17_STDIN_V1: shared stdin is available even without function tests.\n'
    '  const [stdinText, setStdinText] = useState("");\n'
)
OLD_BASIC_CALL = (
    '      void handleApplyStyle(undefined, strictRuntimeValidation, stdinText || undefined);'
)
NEW_BASIC_CALL = (
    '      void handleApplyStyle(undefined, strictRuntimeValidation);'
)
OLD_CASE_CALL = (
    '    void handleApplyStyle(cases, strictRuntimeValidation,\n'
    '      stdinText || (cases.find((test) => Boolean(test.stdin))?.stdin || undefined));'
)
NEW_CASE_CALL = (
    '    void handleApplyStyle(cases, strictRuntimeValidation,\n'
    '      cases.find((test) => Boolean(test.stdin))?.stdin || undefined);'
)
SHARED_UI_START = (
    '          {/* CAPSTONE_BATCH17_STDIN_V1: shared stdin for input() in program and functions */}\n'
)
STEP3 = (
    '          {/* ========================================= */}\n'
    '          {/* Step 03: 함수 반환값 검증 */}'
)
OLD_HELP = (
    '                            입력 예: 5 (한 번), 5와 10 (두 줄). 비워두면 위의 공통 stdin을 사용합니다.\n'
    '                            공통 입력이 비어 있으면 첫 번째 개별 입력을 기본 실행에도 사용합니다.'
)
NEW_HELP = (
    '                            입력 예: 5 (한 번), 5와 10 (두 줄). 대괄호 없이 각 줄에 입력합니다.\n'
    '                            여러 테스트 중 첫 번째로 작성한 stdin을 기본 실행 비교에도 사용합니다.\n'
    '                            함수별 입력은 해당 함수 테스트에서 각각 사용됩니다.'
)


def patch(source: str) -> tuple[str, bool]:
    """Patch only the Batch 17 component; fail closed on unknown layouts."""
    if MARK in source:
        if any(part in source for part in (SHARED_UI_START, OLD_STATE, OLD_BASIC_CALL)):
            raise RuntimeError('Batch 18 marker exists but obsolete shared-stdin UI remains.')
        return source, False

    anchors = (OLD_STATE, OLD_BASIC_CALL, OLD_CASE_CALL, SHARED_UI_START, STEP3, OLD_HELP)
    for anchor in anchors:
        count = source.count(anchor)
        if count != 1:
            raise RuntimeError(f'Expected one Batch 17 anchor, found {count}: {anchor[:90]!r}')
    start = source.index(SHARED_UI_START)
    end = source.index(STEP3, start)
    if start >= end or end - start > 2600:
        raise RuntimeError('Unexpected shared-stdin UI span. Nothing changed.')
    span = source[start:end]
    for name in ('id="shared-stdin"', 'value={stdinText}', 'setStdinText'):
        if name not in span:
            raise RuntimeError(f'Shared-stdin UI mismatch: missing {name}')

    output = source.replace(OLD_STATE, '', 1)
    output = output.replace(OLD_BASIC_CALL, NEW_BASIC_CALL, 1)
    output = output.replace(OLD_CASE_CALL, NEW_CASE_CALL, 1)
    start2 = output.index(SHARED_UI_START)
    end2 = output.index(STEP3, start2)
    output = (
        output[:start2]
        + f'          {{/* {MARK}: stdin is provided inside each function test. */}}\n'
        + output[end2:]
    )
    output = output.replace(OLD_HELP, NEW_HELP, 1)

    if 'id="shared-stdin"' in output or 'setStdinText' in output or 'stdinText ||' in output:
        raise RuntimeError('Shared stdin reference remains; aborting installation.')
    if ('value={draft.stdinText}' not in output
            or 'updateFunctionDraft(draft.id, "stdinText", event.target.value)' not in output
            or 'cases.find((test) => Boolean(test.stdin))?.stdin' not in output):
        raise RuntimeError('Per-function stdin was modified or lost; aborting.')
    if source == output:
        raise RuntimeError('No change detected.')
    return output, True


def _read(path: Path) -> tuple[str, str, bool]:
    data = path.read_bytes()
    bom = data.startswith(b'\xef\xbb\xbf')
    source = data.decode('utf-8-sig')
    if '\r\n' in source and ('\n' in source.replace('\r\n', '')):
        raise RuntimeError('Mixed line endings; manual review required.')
    eol = '\r\n' if '\r\n' in source else '\n'
    return source.replace('\r\n', '\n'), eol, bom


def _encode(source: str, eol: str, bom: bool) -> bytes:
    content = source.replace('\n', eol).encode('utf-8')
    return (b'\xef\xbb\xbf' if bom else b'') + content


def install(root: Path, check: bool) -> str:
    path = root / TARGET
    if not path.is_file():
        raise RuntimeError(f'Missing file: {TARGET}')
    source, eol, bom = _read(path)
    updated, changed = patch(source)
    if not changed:
        return 'Already installed: Batch 18 shared-stdin removal.'
    if check:
        return 'Check passed: only frontend/components/sections/StyleApplySection.tsx will be updated.'

    backup_dir = root / '.git' / 'capstone_batch18_backups'
    if not (root / '.git').is_dir():
        raise RuntimeError('Git directory missing; installation cancelled before writing.')
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / 'StyleApplySection.tsx.before_batch18'
    original = path.read_bytes()
    if backup.exists() and backup.read_bytes() != original:
        raise RuntimeError('Existing backup does not match current source; installation cancelled.')
    if not backup.exists():
        backup.write_bytes(original)

    payload = _encode(updated, eol, bom)
    handle = None
    temp_path = None
    try:
        handle, temp_name = tempfile.mkstemp(prefix='.batch18_', suffix='.tsx', dir=path.parent)
        temp_path = Path(temp_name)
        with os.fdopen(handle, 'wb') as fp:
            handle = None
            fp.write(payload)
        os.replace(temp_path, path)
    finally:
        if handle is not None:
            os.close(handle)
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return 'Installed Batch 18: removed only shared stdin UI; retained function-specific stdin.'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate without editing files')
    args = parser.parse_args()
    try:
        print(install(ROOT, check=args.check))
    except (RuntimeError, UnicodeError, OSError, ValueError) as exc:
        print(f'Batch 18 installation stopped: {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
