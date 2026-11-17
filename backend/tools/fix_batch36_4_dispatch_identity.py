"""Batch36-4 compatibility hotfix: restore the original safe-list dispatcher.

Leaves the canonical action-to-callable identity untouched while applying the
narrow closed composite fallback only after the legacy transformer makes no
change. Existing semantic verification, preflight, and diagnostics remain intact.

From project root:
    python backend/tools/fix_batch36_4_dispatch_identity.py --check
    python backend/tools/fix_batch36_4_dispatch_identity.py --apply
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path

TARGET = Path('backend/app/services/style_apply_service.py')
MARKER = 'CAPSTONE_BATCH36_4_CANONICAL_DISPATCH_COMPAT_V1'
BAD_MAP = '"create_safe_comprehension_collection": transform_safe_composite_list_comprehension,'
GOOD_MAP = '"create_safe_comprehension_collection": transform_for_append_to_list_comprehension,'
OLD_TRY = (
    '    before = code\n'
    '    try:\n'
    '        after = transform_func(code)\n'
    '    except Exception as error:\n'
)
NEW_TRY = (
    '    before = code\n'
    '    try:\n'
    '        after = transform_func(code)\n'
    '        # ' + MARKER + '\n'
    '        # Keep the original dispatcher function identity for older callers.\n'
    '        # Only use the Batch36-4 closed composite pattern as a fallback when\n'
    '        # the existing transformer could not change the current source.\n'
    '        if action == "create_safe_comprehension_collection" and after == before:\n'
    '            after = transform_safe_composite_list_comprehension(before)\n'
    '    except Exception as error:\n'
)
REQUIRED_IMPORT = 'from app.services.improvement.safe_composite_list_service import (\n    transform_safe_composite_list_comprehension,\n)'


def patch(source: bytes) -> tuple[bytes, str]:
    """Fail closed on unexpected source, preserve LF/CRLF, and be idempotent."""
    if not isinstance(source, bytes):
        raise TypeError('Expected source bytes')
    decoded = source.decode('utf-8')
    normalized = decoded.replace('\r\n', '\n')
    marker_count = normalized.count(MARKER)
    if marker_count:
        if (marker_count == 1 and normalized.count(GOOD_MAP) == 1
                and BAD_MAP not in normalized
                and normalized.count(NEW_TRY) == 1
                and REQUIRED_IMPORT in normalized):
            ast.parse(normalized)
            return source, 'already_applied'
        raise RuntimeError('Partial or duplicated 36-4 compatibility marker: refusing to modify')
    if normalized.count(BAD_MAP) != 1 or GOOD_MAP in normalized:
        raise RuntimeError('Expected exactly one 36-4 composite dispatcher override')
    if normalized.count(OLD_TRY) != 1:
        raise RuntimeError('Expected exactly one unchanged action invocation block')
    if normalized.count(REQUIRED_IMPORT) != 1:
        raise RuntimeError('Batch36-4 composite import missing or ambiguous')
    revised = normalized.replace(BAD_MAP, GOOD_MAP, 1).replace(OLD_TRY, NEW_TRY, 1)
    ast.parse(revised)
    if '\r\n' in decoded:
        revised = revised.replace('\n', '\r\n')
    return revised.encode('utf-8'), 'ready'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Restore Batch36-4 legacy action callable identity')
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument('--check', action='store_true')
    operation.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if not TARGET.is_file():
        parser.error('File not found: ' + str(TARGET) + '; run from the repository root')
    original = TARGET.read_bytes()
    try:
        updated, status = patch(original)
    except (SyntaxError, UnicodeError, TypeError, RuntimeError) as exc:
        parser.error(str(exc))
    if args.check:
        print('36-4 canonical dispatcher check:', status)
    elif status == 'ready':
        TARGET.write_bytes(updated)
        print('36-4 canonical dispatcher restored:', TARGET)
    else:
        print('36-4 compatibility hotfix already applied:', TARGET)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
