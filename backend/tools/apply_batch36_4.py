"""Install Batch36-4 as an idempotent, fail-closed modification.

Run from repository root:
    python backend/tools/apply_batch36_4.py --check
    python backend/tools/apply_batch36_4.py --apply
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path

MARKER = 'CAPSTONE_BATCH36_4_PURE_COMPOSITE_V1'
OLD_IMPORT = '''from app.services.improvement.safe_list_comprehension_service import (
    transform_for_append_to_list_comprehension,
    transform_list_comprehension_to_for_append,
)
'''
NEW_IMPORT = OLD_IMPORT + f'''# {MARKER}
from app.services.improvement.safe_composite_list_service import (
    transform_safe_composite_list_comprehension,
)
'''
OLD_MAP = '"create_safe_comprehension_collection": transform_for_append_to_list_comprehension,'
NEW_MAP = '"create_safe_comprehension_collection": transform_safe_composite_list_comprehension,'


def patch(source: bytes) -> tuple[bytes, str]:
    """Apply only if exact original import and dispatcher mapping are present."""
    newline = b'\r\n' if b'\r\n' in source else b'\n'
    text = source.decode('utf-8')
    normal = text.replace('\r\n', '\n')
    if MARKER in normal:
        if normal.count(MARKER) == 1 and NEW_IMPORT in normal and NEW_MAP in normal:
            return source, 'already_applied'
        raise RuntimeError('36-4 partial marker detected; refusing to modify')
    if normal.count(OLD_IMPORT) != 1 or normal.count(OLD_MAP) != 1:
        raise RuntimeError('Expected dispatch anchors missing or ambiguous; refusing to modify')
    if NEW_MAP in normal:
        raise RuntimeError('Unexpected partial dispatcher modification')
    modified = normal.replace(OLD_IMPORT, NEW_IMPORT).replace(OLD_MAP, NEW_MAP)
    ast.parse(modified)
    raw = modified.replace('\n', '\r\n').encode('utf-8') if newline == b'\r\n' else modified.encode('utf-8')
    return raw, 'ready'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Batch36-4 guarded install')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    newfile = root / 'app/services/improvement/safe_composite_list_service.py'
    if not newfile.is_file():
        parser.error('Missing new composite module: ' + str(newfile))
    ast.parse(newfile.read_text(encoding='utf-8'))
    dst = root / 'app/services/style_apply_service.py'
    before = dst.read_bytes()
    output, status = patch(before)
    print('36-4 composite module:', newfile.relative_to(root))
    print('style_apply_service.py:', status)
    if args.apply and status == 'ready':
        dst.write_bytes(output)
        print('Patch applied. Run unit tests and the full regression suite.')
    elif args.check:
        print('Check only: existing source not modified.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
