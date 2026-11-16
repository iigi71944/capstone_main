"""Install Batch 22 on GitHub main 12de94c, without blind overwrite.

At capstone_main repository root:
    python backend/tools/install_batch22.py --check
    python backend/tools/install_batch22.py

Preflight verifies the exact four expected source files before any writes.
Originals are backed up under .git/capstone_batch22_backups/.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = Path('backend/tools/batch22_payload')
ORIGINALS = {
    Path('backend/app/services/style_tag_transform_map_service.py'): 'a463214bd71646cbdc3411092b2a9dda6b1fe3a3',
    Path('backend/app/services/style_transform_plan_service.py'): '2317775709d5617c76be18f681c7d16fe7cd0921',
    Path('backend/app/services/style_apply_service.py'): 'b07774a91908d758a21426f7bceb220ea5418a88',
    Path('backend/tests/test_style_batch21_new_links.py'): 'a76f92bf6353f96c8eaa97d3392082774cc1aa04',
}
NEW_FILES = {
    Path('backend/app/services/improvement/safe_batch22_service.py'):
        PAYLOAD / 'safe_batch22_service.py.source',
    Path('backend/tests/test_style_batch22_new_links.py'):
        PAYLOAD / 'test_style_batch22_new_links.py.source',
    Path('backend/tools/audit_transform_batch22.py'):
        PAYLOAD / 'audit_transform_batch22.py.source',
}
MARK = 'CAPSTONE_BATCH22_'


def _replace_once(text: str, before: str, after: str, where: str) -> str:
    count = text.count(before)
    if count != 1:
        raise RuntimeError(f'{where}: expected one anchor, found {count}; no changes made')
    return text.replace(before, after, 1)


def _registry_keys(source: str):
    tree = ast.parse(source)
    matches = [node.value for node in tree.body
               if isinstance(node, ast.AnnAssign)
               and isinstance(node.target, ast.Name)
               and node.target.id == 'CREATE_ACTION_BY_TAG'
               and isinstance(node.value, ast.Dict)]
    if len(matches) != 1:
        raise RuntimeError('Registry: expected exactly one dictionary')
    if any(not isinstance(k, ast.Constant) or not isinstance(k.value, str)
           for k in matches[0].keys):
        raise RuntimeError('Registry: keys are not all literal strings')
    return [k.value for k in matches[0].keys]


def patch_registry(source: str) -> str:
    if MARK in source:
        raise RuntimeError('Batch22 partial registry change detected')
    before = _registry_keys(source)
    if len(before) != 84 or len(set(before)) != 84:
        raise RuntimeError('Expected 84 unique linked tags from Batch21')
    if {'변수 할당', 'raise문'} & set(before):
        raise RuntimeError('Batch22 tags already registered unexpectedly')
    result = _replace_once(source,
        'CREATE_ACTION_BY_TAG: dict[str, str] = {\n',
        'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
        '    # CAPSTONE_BATCH22_REGISTRY_V1: safe literal unpack and debug raise.\n'
        '    "변수 할당": "create_safe_literal_unpack_assignments",\n'
        '    "raise문": "create_safe_debug_raise",\n',
        'Batch22 registry')
    keys = _registry_keys(result)
    if len(keys) != 86 or len(set(keys)) != 86:
        raise RuntimeError('Registry validation failed after Batch22 patch')
    return result


def patch_plan(source: str) -> str:
    if MARK in source:
        raise RuntimeError('Batch22 partial plan change detected')
    result = _replace_once(source,
        '    "annotation": {"create_safe_local_annotation", "create_safe_local_deannotation"},\n',
        '    "annotation": {"create_safe_local_annotation", "create_safe_local_deannotation"},\n'
        '    # CAPSTONE_BATCH22_ASSERT_RAISE_CONFLICT_V1\n'
        '    "assert_raise": {"create_safe_debug_assert", "create_safe_debug_raise"},\n',
        'Batch22 direction conflict')
    gate = '''    # CAPSTONE_BATCH22_METRIC_GATE_V1: derive preference from stored metrics.
    # Unpacking constants is local and side-effect free. Debug assert expansion
    # keeps the explicit optimization guard; neither action is triggered by a
    # missing-tag label alone.
    saved_b22 = _get_style_metrics(diff)
    target_b22 = _get_target_metrics(diff)
    if (_metric_count(saved_b22, "assign_count") >
            _metric_count(target_b22, "assign_count") > 0
            and _metric_count(target_b22, "tuple_literal_count") > 0):
        actions.append({
            "tag": "변수 할당",
            "action": "create_safe_literal_unpack_assignments",
            "reason": "저장 스타일의 개별 대입문 선호와 상수 튜플 언패킹이 모두 확인된 경우에만 분리합니다.",
        })
    if (_metric_count(saved_b22, "raise_count") > 0
            and _metric_count(target_b22, "raise_count") == 0
            and _metric_count(target_b22, "assert_count") > 0
            and _metric_count(target_b22, "if_count") > 0):
        actions.append({
            "tag": "raise문",
            "action": "create_safe_debug_raise",
            "reason": "__debug__로 보호된 단순 assert만 명시적 예외 발생으로 변환합니다.",
        })

'''
    result = _replace_once(result,
        '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n',
        gate + '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n',
        'Batch22 plan gate')
    result = _replace_once(result,
        '        # CAPSTONE_BATCH21_METRIC_ONLY_V1: unobserved tag name is not enough.\n',
        '        # CAPSTONE_BATCH22_METRIC_ONLY_V1: no blind transforms from a missing tag.\n'
        '        if tag_name in {"변수 할당", "raise문"}:\n'
        '            continue\n'
        '        # CAPSTONE_BATCH21_METRIC_ONLY_V1: unobserved tag name is not enough.\n',
        'Batch22 tag guard')
    ast.parse(result)
    return result


def patch_dispatch(source: str) -> str:
    if MARK in source:
        raise RuntimeError('Batch22 partial dispatcher change detected')
    result = _replace_once(source,
        'def _get_transform_function(action: str):\n',
        '# CAPSTONE_BATCH22_DISPATCH_IMPORT_V1\n'
        'from app.services.improvement.safe_batch22_service import (\n'
        '    transform_literal_unpack_to_assignments,\n'
        '    transform_debug_assert_to_raise,\n'
        ')\n\n'
        'def _get_transform_function(action: str):\n',
        'Batch22 dispatcher import')
    result = _replace_once(result,
        '    action_map = {\n',
        '    action_map = {\n'
        '        # CAPSTONE_BATCH22_DISPATCH_MAP_V1\n'
        '        "create_safe_literal_unpack_assignments": transform_literal_unpack_to_assignments,\n'
        '        "create_safe_debug_raise": transform_debug_assert_to_raise,\n',
        'Batch22 dispatcher map')
    ast.parse(result)
    return result


def patch_legacy_tests(source: str) -> str:
    if MARK in source:
        raise RuntimeError('Batch22 partial legacy-test patch detected')
    result = _replace_once(source,
        '        self.assertEqual(len(CREATE_ACTION_BY_TAG), 84)\n'
        '        self.assertEqual(len(COMPARE_ONLY_TAGS), 18)\n',
        '        # CAPSTONE_BATCH22_LEGACY_REGISTRY_V1: keep old expectations valid after extensions.\n'
        '        self.assertGreaterEqual(len(CREATE_ACTION_BY_TAG), 84)\n'
        '        self.assertLessEqual(len(COMPARE_ONLY_TAGS), 18)\n'
        '        self.assertEqual(len(CREATE_ACTION_BY_TAG) + len(COMPARE_ONLY_TAGS), 102)\n',
        'Batch22 legacy test')
    ast.parse(result)
    return result


def _blob_sha(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def _read_source(path: Path):
    raw = path.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    value = raw[3:] if bom else raw
    if b'\r\n' in value and b'\n' in value.replace(b'\r\n', b''):
        raise RuntimeError(f'Mixed Windows/POSIX line endings: {path}')
    eol = '\r\n' if b'\r\n' in value else '\n'
    normalized = value.replace(b'\r\n', b'\n')
    return normalized.decode('utf-8'), eol, bom, raw, normalized


def _encoded(source: str, eol: str, bom: bool) -> bytes:
    return (b'\xef\xbb\xbf' if bom else b'') + source.replace('\n', eol).encode('utf-8')


def prepare(root: Path, *, enforce_sha=True):
    if not (root / '.git').is_dir():
        raise RuntimeError('Run from capstone_main Git repository root (missing .git).')
    patches = {
        Path('backend/app/services/style_tag_transform_map_service.py'): patch_registry,
        Path('backend/app/services/style_transform_plan_service.py'): patch_plan,
        Path('backend/app/services/style_apply_service.py'): patch_dispatch,
        Path('backend/tests/test_style_batch21_new_links.py'): patch_legacy_tests,
    }
    staged: dict[Path, bytes] = {}
    backups: dict[Path, bytes] = {}
    flags = []
    for rel, patch in patches.items():
        path = root / rel
        if not path.is_file():
            raise RuntimeError(f'Missing expected file: {rel}')
        source, eol, bom, raw, normalized = _read_source(path)
        present = MARK in source
        flags.append(present)
        if present:
            if rel.name == 'style_tag_transform_map_service.py':
                keys = _registry_keys(source)
                if len(keys) != 86 or len(set(keys)) != 86:
                    raise RuntimeError('Partially applied Batch22 registry')
            continue
        if enforce_sha and _blob_sha(normalized) != ORIGINALS[rel]:
            raise RuntimeError(f'Unexpected edited source since 12de94c: {rel}. '
                               'No files modified; reconcile local changes first.')
        updated = patch(source)
        staged[rel] = _encoded(updated, eol, bom)
        backups[rel] = raw
    new_flags = []
    for rel, payload in NEW_FILES.items():
        path = root / rel
        payload_path = root / payload
        if not payload_path.is_file():
            raise RuntimeError(f'Missing ZIP payload: {payload}')
        value = payload_path.read_bytes()
        ast.parse(value.decode('utf-8'))
        exists = path.exists()
        new_flags.append(exists)
        if exists:
            if path.read_bytes() != value:
                raise RuntimeError(f'Existing file does not match Batch22 payload: {rel}')
        else:
            staged[rel] = value
    if (any(flags) or any(new_flags)) and not (all(flags) and all(new_flags)):
        raise RuntimeError('Partial Batch22 installation detected. No files changed.')
    return staged, backups


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.capstone_b22_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(root: Path, *, check=False, enforce_sha=True) -> str:
    staged, backups = prepare(root, enforce_sha=enforce_sha)
    if not staged:
        return 'Batch22 already installed; no files changed.'
    if check:
        return f'Batch22 preflight passed: {len(staged)} files ready; no files modified.'
    backup_root = root / '.git' / 'capstone_batch22_backups'
    backup_root.mkdir(parents=True, exist_ok=True)
    for rel, old in backups.items():
        dst = backup_root / rel
        if dst.exists() and dst.read_bytes() != old:
            raise RuntimeError(f'Backup differs from the original: {dst}')
        if not dst.exists():
            _atomic_write(dst, old)
    done = []
    try:
        for rel, value in staged.items():
            _atomic_write(root / rel, value)
            done.append(rel)
    except Exception:
        for rel in reversed(done):
            if rel in backups:
                _atomic_write(root / rel, backups[rel])
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    return f'Installed Batch22: {len(done)} files; two new conservative transforms.'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(install(ROOT, check=args.check))
        return 0
    except (RuntimeError, OSError, SyntaxError, ValueError, UnicodeError) as error:
        print(f'Batch22 installation stopped: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
