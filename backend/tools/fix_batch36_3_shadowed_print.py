"""36-3 hotfix: never treat a shadowed ``print`` call as an ordinary keyword call.

Apply only after apply_batch36_3.py has been run. The patch is conservative,
checks its exact anchor, supports Windows CRLF, and is idempotent.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGET = Path('app/services/improvement/safe_structural_patterns_service.py')
REQUIRES = 'CAPSTONE_BATCH36_3_NESTED_KEYWORD_V1'
MARKER = 'CAPSTONE_BATCH36_3_SHADOWED_PRINT_GUARD_V1'
BEFORE = '''                    if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                        signature = _module_function(tree, call.func.id, i)
                        if signature is not None:
                            replacements = _change_call(stmt, signature, direction)
                if replacements is None and direction == 'to_keywords':
                    replacements = _change_wrapped_print_call(tree, stmt, i)'''
AFTER = '''                    # CAPSTONE_BATCH36_3_SHADOWED_PRINT_GUARD_V1:
                    # A user-defined print(x) is NOT the builtin print().
                    # Keep the dedicated nested-print safety gate responsible
                    # for print(fn(literals)); never rewrite outer print(...)
                    # into print(x=...) when print is shadowed.
                    if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                            and not (direction == 'to_keywords' and call.func.id == 'print')):
                        signature = _module_function(tree, call.func.id, i)
                        if signature is not None:
                            replacements = _change_call(stmt, signature, direction)
                if replacements is None and direction == 'to_keywords':
                    replacements = _change_wrapped_print_call(tree, stmt, i)'''


def patch(raw: bytes) -> tuple[bytes, str]:
    newline = '\r\n' if b'\r\n' in raw else '\n'
    source = raw.decode('utf-8').replace('\r\n', '\n')
    if REQUIRES not in source:
        raise RuntimeError('36-3 기본 패치가 적용되지 않았습니다. 먼저 apply_batch36_3.py --apply를 실행하세요.')
    if MARKER in source:
        if source.count(MARKER) != 1 or AFTER not in source:
            raise RuntimeError('수정 마커가 불완전하거나 중복됩니다. 자동 수정을 중단했습니다.')
        return raw, 'already_applied'
    count = source.count(BEFORE)
    if count != 1:
        raise RuntimeError(f'예상 코드 위치 불일치({count}개). 다른 변경사항을 덮어쓰지 않았습니다.')
    updated = source.replace(BEFORE, AFTER, 1)
    ast.parse(updated, filename=str(TARGET))
    return updated.replace('\n', newline).encode('utf-8'), 'ready'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='36-3 shadowed print safety hotfix')
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--check', action='store_true')
    modes.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    path = ROOT / TARGET
    try:
        if not path.is_file():
            raise RuntimeError('원본 서비스 파일을 찾을 수 없습니다: ' + str(path))
        updated, status = patch(path.read_bytes())
        print('36-3 shadowed print fix:', status)
        if args.apply and status == 'ready':
            path.write_bytes(updated)
            print('수정 적용 완료: 사용자 정의 print(...)는 키워드 호출 변환에서 제외됩니다.')
        elif args.check:
            print('적용 가능 여부만 검사했습니다 (파일 수정 없음).')
        return 0
    except (OSError, ValueError, UnicodeError, RuntimeError) as error:
        print('36-3 수정 중단:', error, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
