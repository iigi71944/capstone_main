"""Fail-closed, idempotent hotfix for R08's spurious nested keyword rewrite.

Run in repository root:
  python backend/tools/fix_batch36_4_r08_unused_parameter.py --check
  python backend/tools/fix_batch36_4_r08_unused_parameter.py --apply
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path

TARGET = Path('backend/app/services/improvement/safe_structural_patterns_service.py')
MARKER = 'CAPSTONE_BATCH36_4_UNUSED_PARAMETER_GUARD_V1'
OLD = (
    '    signature = _module_function(tree, inner.func.id, index)\n'
    '    if signature is None or len(inner.args) != len(signature):\n'
    '        return None\n'
    '    updated = copy.deepcopy(stmt)\n'
)
NEW = (
    '    signature = _module_function(tree, inner.func.id, index)\n'
    '    if signature is None or len(inner.args) != len(signature):\n'
    '        return None\n'
    '    # ' + MARKER + ': avoid keyword-only surface edits when the helper\n'
    '    # ignores its declared parameters (R08); preserve the previous\n'
    '    # function/keyword safety checks and the R43 valid transformation.\n'
    '    helper = tree.body[0]\n'
    '    if not all(\n'
    '        any(isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)\n'
    '            and node.id == name for node in ast.walk(helper))\n'
    '        for name in signature\n'
    '    ):\n'
    '        return None\n'
    '    updated = copy.deepcopy(stmt)\n'
)


def patch(data: bytes) -> tuple[bytes, str]:
    if not isinstance(data, bytes):
        raise TypeError('expected bytes')
    if MARKER.encode('ascii') in data:
        if data.count(MARKER.encode('ascii')) != 1:
            raise RuntimeError('multiple hotfix markers; refusing')
        ast.parse(data.decode('utf-8'))
        return data, 'already_applied'
    newline = '\r\n' if b'\r\n' in data else '\n'
    text = data.decode('utf-8')
    # Keep a single newline convention when patching Windows-checked-out files.
    old = OLD.replace('\n', newline)
    new = NEW.replace('\n', newline)
    if text.count(old) != 1 or '_change_wrapped_print_call(' not in text:
        raise RuntimeError('expected 36-3 nested call guard was not found uniquely; refusing')
    modified = text.replace(old, new, 1)
    ast.parse(modified)
    return modified.encode('utf-8'), 'ready'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Batch36-4 R08 unused argument hotfix')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if not TARGET.is_file():
        parser.error(f'파일 없음: {TARGET}. 프로젝트 루트에서 실행하세요.')
    original = TARGET.read_bytes()
    try:
        changed, status = patch(original)
    except (RuntimeError, TypeError, UnicodeError, SyntaxError) as error:
        parser.error(str(error))
    if args.check:
        print('36-4 R08 hotfix 확인:', status)
    elif status == 'ready':
        TARGET.write_bytes(changed)
        print('36-4 R08 hotfix 적용 완료:', TARGET)
    else:
        print('이미 적용되었습니다:', TARGET)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
