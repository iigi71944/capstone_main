"""Install Batch36-2's narrow, reviewable string-strip fix.

The ZIP places additive audit/test files in their final locations. This script
patches only one production file, and refuses unknown/upstream variants.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'app/services/improvement/safe_batch29_service.py'
MARKER = 'CAPSTONE_BATCH36_2_SAFE_NAMED_STRIP_V1'

OLD_CALL = '''    for call in _assignment_calls(tree):
        func = call.func
        if not (isinstance(func, ast.Attribute) and func.attr == 'strip'
                and isinstance(func.value, ast.Constant)
                and type(func.value.value) is str and not call.keywords):
            continue
'''
NEW_CALL = '''    for call in _assignment_calls(tree):
        func = call.func
        if not (isinstance(func, ast.Attribute) and func.attr == 'strip'
                and not call.keywords):
            continue
        receiver = func.value
        # CAPSTONE_BATCH36_2_SAFE_NAMED_STRIP_V1: a provably unchanged local
        # module-level string constant is also a safe receiver. Refuse shadowed,
        # rebound, deleted, imported, computed, or scoped variable bindings.
        if isinstance(receiver, ast.Constant):
            if type(receiver.value) is not str:
                continue
        elif isinstance(receiver, ast.Name):
            if not _single_literal_string_binding(tree, receiver.id, call.lineno):
                continue
        else:
            continue
'''

INSERT_BEFORE = 'def _strip_default(code, explicit):\n'
HELPER = '''def _single_literal_string_binding(tree, name, call_line):
    """Allow a top-level str assignment, written exactly once before a call.

    This is intentionally narrow; no interprocedural inference, name aliasing,
    rebinding, import, deletion or mutable receiver type is accepted. The
    caller also enforces the pre-existing _safe_module code restrictions.
    """
    bindings = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == name
        and isinstance(node.ctx, (ast.Store, ast.Del))
    ]
    if len(bindings) != 1 or not isinstance(bindings[0].ctx, ast.Store):
        return False
    for stmt in tree.body:
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id == name and stmt.lineno < call_line
                and isinstance(stmt.value, ast.Constant)
                and type(stmt.value.value) is str):
            return True
    return False


'''


def _read():
    if not TARGET.is_file():
        raise RuntimeError(f'대상 서비스 파일 없음: {TARGET}')
    return TARGET.read_bytes()


def _patch(original: bytes) -> tuple[bytes, str]:
    newline = '\r\n' if b'\r\n' in original else '\n'
    source = original.decode('utf-8').replace('\r\n', '\n')
    if MARKER in source:
        if (source.count(MARKER) != 1
                or source.count('def _single_literal_string_binding(') != 1
                or source.count('if not _single_literal_string_binding(') != 1):
            raise RuntimeError('36-2 부분 적용 의심: 손상된 패치를 덮어쓰지 않습니다.')
        return original, 'already_applied'
    if source.count(OLD_CALL) != 1 or source.count(INSERT_BEFORE) != 1:
        raise RuntimeError('원본 앵커 불일치: 기존 소스 버전과 다릅니다. 수정하지 않았습니다.')
    if '_single_literal_string_binding' in source:
        raise RuntimeError('기존에 동일한 이름의 함수가 있어 수정하지 않았습니다.')
    patched = source.replace(INSERT_BEFORE, HELPER + INSERT_BEFORE, 1).replace(OLD_CALL, NEW_CALL, 1)
    if patched.count(MARKER) != 1:
        raise RuntimeError('패치 무결성 검사 실패')
    ast.parse(patched, filename=str(TARGET))
    return patched.replace('\n', newline).encode('utf-8'), 'ready'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--check', action='store_true', help='패치 가능 여부만 검사')
    action.add_argument('--apply', action='store_true', help='검증한 앵커에만 패치 적용')
    args = parser.parse_args(argv)
    try:
        before = _read()
        after, status = _patch(before)
        if args.apply and status == 'ready':
            # Only one production file is edited. Do not touch unrelated files.
            TARGET.write_bytes(after)
            print('36-2 문자열 변수 strip 안전 변환 개선 적용 완료')
        elif status == 'already_applied':
            print('36-2 이미 적용됨 (중복 수정 없음)')
        else:
            print('36-2 패치 앵커 검사 통과, 적용 가능')
        return 0
    except (RuntimeError, OSError, UnicodeError) as e:
        print('36-2 패치 중단:', e, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
