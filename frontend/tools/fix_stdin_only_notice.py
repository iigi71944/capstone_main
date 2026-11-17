#!/usr/bin/env python3
"""Hide the function-result-unavailable warning for stdin-only requests.

Run from capstone_main root:
    python3 frontend/tools/fix_stdin_only_notice.py --check
    python3 frontend/tools/fix_stdin_only_notice.py --apply

Changes a *single JSX condition*; it does not change visual styling, backend,
function-verification behavior, or input submission. Fail closed on drift.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

TARGET = Path('frontend/components/sections/StyleApplySection.tsx')
PREVIOUS_PATCH_MARKER = 'CAPSTONE_STDIN_ONLY_INDEPENDENT_FUNCTION_CASES_V1'
MARKER = 'CAPSTONE_STDIN_ONLY_HIDE_UNREQUESTED_FUNCTION_NOTICE_V1'
OLD = '            {!functionVerification && useFunctionTests && styleApplyResult && ('
NEW = '''            {/* CAPSTONE_STDIN_ONLY_HIDE_UNREQUESTED_FUNCTION_NOTICE_V1:
                No function name means only top-level stdin was verified. */}
            {!functionVerification &&
              useFunctionTests &&
              functionDrafts.some((draft) => draft.functionName.trim() !== "") &&
              styleApplyResult && ('''


def patch_source(original: str) -> tuple[str, str]:
    """Return (patched_source, ready|already_applied) without writing anything."""
    if not isinstance(original, str):
        raise ValueError('소스는 UTF-8 텍스트여야 합니다.')
    crlf = '\r\n' in original
    if crlf and original.count('\r\n') != original.count('\n'):
        raise ValueError('혼합된 줄바꿈이 감지되어 변경하지 않습니다.')
    text = original.replace('\r\n', '\n')
    if MARKER in text:
        if text.count(MARKER) != 1 or text.count(NEW) != 1 or OLD in text:
            raise ValueError('부분 적용된 파일이 발견되었습니다. 수동 확인이 필요합니다.')
        return original, 'already_applied'
    if PREVIOUS_PATCH_MARKER not in text:
        raise ValueError('이전 stdin 단독 검증 패치가 적용되지 않았습니다. 먼저 이전 수정본을 적용해주세요.')
    if 'import { parseVerificationInputs } from "../../lib/verificationInputSelection";' not in text:
        raise ValueError('이전 stdin 단독 검증 패치의 import가 없습니다.')
    if text.count(OLD) != 1:
        raise ValueError('수정하려는 결과 안내 조건식이 한 번만 나타나지 않습니다. 변경하지 않습니다.')
    if text.count('함수 테스트 결과를 확인할 수 없습니다.') != 1:
        raise ValueError('함수 검증 안내 구성이 달라졌습니다. 변경하지 않습니다.')
    revised = text.replace(OLD, NEW, 1)
    if crlf:
        revised = revised.replace('\n', '\r\n')
    return revised, 'ready'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='stdin-only function notice frontend hotfix')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true', help='검사만 수행')
    group.add_argument('--apply', action='store_true', help='조건식 변경 적용')
    args = parser.parse_args(argv)
    if not TARGET.is_file():
        parser.error('capstone_main 프로젝트 루트에서 실행해주세요: ' + str(TARGET))
    try:
        content = TARGET.read_bytes()
        revised, status = patch_source(content.decode('utf-8'))
        if args.check:
            print('stdin-only notice check:', status)
            return 0
        if status == 'already_applied':
            print('stdin-only notice patch: already_applied')
            return 0
        # Atomic replacement; keep permissions.
        temp = TARGET.with_name(TARGET.name + '.stdin_notice_tmp')
        try:
            temp.write_bytes(revised.encode('utf-8'))
            temp.chmod(TARGET.stat().st_mode)
            os.replace(temp, TARGET)
        finally:
            if temp.exists():
                temp.unlink()
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    print('stdin-only notice patch: applied')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
