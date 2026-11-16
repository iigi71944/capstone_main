"""Install Batch 23 only on the expected clean 22nd-batch sources.

Usage from the capstone_main repository root:
  python backend/tools/install_batch23.py --check
  python backend/tools/install_batch23.py

Preflight performs every check before mutation. Originals are copied beneath
.git/capstone_batch23_backups. Installation is atomic per file and rolls back
all written files after an error. Repeated installation is a no-op.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = Path('backend/tools/batch23_payload')
BASE = {
    Path('backend/app/services/style_tag_transform_map_service.py'): '2776f0b07d07aa22aada1ab1b6919778914cfd6b',
    Path('backend/app/services/style_transform_plan_service.py'): '1d3ee51ea628ed73a1551899fe81a5f288b891ea',
    Path('backend/app/services/style_apply_service.py'): '986dbf5aa4168fe9e3ffd8deb9c64eda8c493461',
    Path('backend/tests/test_style_batch22_new_links.py'): 'cc951aa37664d8218c6cc0e62baff64c00080bfe',
}
NEW = {
    Path('backend/app/services/improvement/safe_batch23_service.py'):
        PAYLOAD / 'safe_batch23_service.py.source',
    Path('backend/tests/test_style_batch23_new_links.py'):
        PAYLOAD / 'test_style_batch23_new_links.py.source',
    Path('backend/tools/audit_transform_batch23.py'):
        PAYLOAD / 'audit_transform_batch23.py.source',
}
MARK = 'CAPSTONE_BATCH23_'


def replace_one(source: str, old: str, new: str, label: str):
    number = source.count(old)
    if number != 1:
        raise RuntimeError(f'{label}: expected exactly one anchor, found {number}')
    return source.replace(old, new, 1)


def registry_keys(source: str):
    tree = ast.parse(source)
    nodes = [node.value for node in tree.body
             if isinstance(node, ast.AnnAssign)
             and isinstance(node.target, ast.Name)
             and node.target.id == 'CREATE_ACTION_BY_TAG'
             and isinstance(node.value, ast.Dict)]
    if len(nodes) != 1 or any(not isinstance(key, ast.Constant) or not isinstance(key.value, str)
                              for key in nodes[0].keys):
        raise RuntimeError('Registry dictionary or its keys are invalid')
    return [key.value for key in nodes[0].keys]


def patch_registry(source: str):
    if MARK in source:
        raise RuntimeError('Partial Batch23 registry')
    keys = registry_keys(source)
    if len(keys) != 86 or len(set(keys)) != 86:
        raise RuntimeError(f'Expected 86 unique Batch22 linked tags, found {len(keys)}')
    if {'break문', '전역 변수 사용'} & set(keys):
        raise RuntimeError('Batch23 tag was previously registered')
    after = replace_one(
        source, 'CREATE_ACTION_BY_TAG: dict[str, str] = {\n',
        'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
        '    # CAPSTONE_BATCH23_REGISTRY_V1: guarded break and readonly global.\n'
        '    "break문": "create_safe_counted_break",\n'
        '    "전역 변수 사용": "create_safe_readonly_global",\n',
        'Batch23 registry')
    if len(registry_keys(after)) != 88 or len(set(registry_keys(after))) != 88:
        raise RuntimeError('Batch23 tag count or uniqueness validation failed')
    return after


def patch_plan(source: str):
    if MARK in source:
        raise RuntimeError('Partial Batch23 plan')
    gate = '''    # CAPSTONE_BATCH23_METRIC_GATE_V1: explicit saved preferences only.
    # Avoid introducing break guards when the saved style prefers for loops.
    saved_b23 = _get_style_metrics(diff)
    target_b23 = _get_target_metrics(diff)
    if (_metric_count(saved_b23, "break_count") > 0
            and _metric_count(target_b23, "break_count") == 0
            and _metric_count(target_b23, "loop_count") > 0
            and not prefer_for
            and not any(item.get("action") in {"create_while_iteration", "create_counted_while_to_for"}
                        for item in actions)):
        actions.append({
            "tag": "break문",
            "action": "create_safe_counted_break",
            "reason": "정수 카운터가 명확한 while 반복문에만 종료 조건의 break 가드를 명시합니다.",
        })
    if (_metric_count(saved_b23, "global_count") > 0
            and _metric_count(target_b23, "global_count") == 0
            and _metric_count(target_b23, "function_count") > 0
            and _metric_count(target_b23, "assign_count") > 0):
        actions.append({
            "tag": "전역 변수 사용",
            "action": "create_safe_readonly_global",
            "reason": "모듈에 정의된 상수를 읽기만 하는 단순 함수에 명시적 global 선언을 추가합니다.",
        })

'''
    after = replace_one(source,
        '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n',
        gate + '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n',
        'Batch23 plan gate')
    after = replace_one(after,
        '        # CAPSTONE_BATCH22_METRIC_ONLY_V1: no blind transforms from a missing tag.\n',
        '        # CAPSTONE_BATCH23_METRIC_ONLY_V1: missing tags alone never trigger generation.\n'
        '        if tag_name in {"break문", "전역 변수 사용"}:\n'
        '            continue\n'
        '        # CAPSTONE_BATCH22_METRIC_ONLY_V1: no blind transforms from a missing tag.\n',
        'Batch23 missing-tag gate')
    ast.parse(after)
    return after


def patch_dispatch(source: str):
    if MARK in source:
        raise RuntimeError('Partial Batch23 dispatcher')
    after = replace_one(source,
        'def _get_transform_function(action: str):\n',
        '# CAPSTONE_BATCH23_DISPATCH_IMPORT_V1\n'
        'from app.services.improvement.safe_batch23_service import (\n'
        '    transform_safe_counted_while_to_guard_break,\n'
        '    transform_safe_readonly_global_declaration,\n'
        ')\n\n'
        'def _get_transform_function(action: str):\n',
        'Batch23 dispatcher import')
    after = replace_one(after,
        '    action_map = {\n',
        '    action_map = {\n'
        '        # CAPSTONE_BATCH23_DISPATCH_MAP_V1\n'
        '        "create_safe_counted_break": transform_safe_counted_while_to_guard_break,\n'
        '        "create_safe_readonly_global": transform_safe_readonly_global_declaration,\n',
        'Batch23 dispatcher map')
    ast.parse(after)
    return after


def patch_legacy_test(source: str):
    if MARK in source:
        raise RuntimeError('Partial Batch23 legacy-test patch')
    after = replace_one(source,
        '        self.assertEqual(len(CREATE_ACTION_BY_TAG), 86)\n'
        '        self.assertEqual(len(COMPARE_ONLY_TAGS), 16)\n',
        '        # CAPSTONE_BATCH23_LEGACY_REGISTRY_V1: later linked tags are allowed.\n'
        '        self.assertGreaterEqual(len(CREATE_ACTION_BY_TAG), 86)\n'
        '        self.assertLessEqual(len(COMPARE_ONLY_TAGS), 16)\n'
        '        self.assertEqual(len(CREATE_ACTION_BY_TAG) + len(COMPARE_ONLY_TAGS), 102)\n',
        'Batch23 baseline-test compatibility')
    ast.parse(after)
    return after


def _git_blob_sha(payload: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(payload)).encode('ascii') + b'\0' + payload).hexdigest()


def _read_source(path: Path):
    original = path.read_bytes()
    bom = original.startswith(b'\xef\xbb\xbf')
    data = original[3:] if bom else original
    if b'\r\n' in data and b'\n' in data.replace(b'\r\n', b''):
        raise RuntimeError(f'Mixed line endings: {path}')
    eol = '\r\n' if b'\r\n' in data else '\n'
    normalized = data.replace(b'\r\n', b'\n')
    return normalized.decode('utf-8'), eol, bom, original, normalized


def _encode(source: str, eol: str, bom: bool):
    return (b'\xef\xbb\xbf' if bom else b'') + source.replace('\n', eol).encode('utf-8')


def prepare(root: Path, enforce_sha: bool = True):
    if not (root / '.git').is_dir():
        raise RuntimeError('Run from capstone_main Git repository root')
    patches = {
        Path('backend/app/services/style_tag_transform_map_service.py'): patch_registry,
        Path('backend/app/services/style_transform_plan_service.py'): patch_plan,
        Path('backend/app/services/style_apply_service.py'): patch_dispatch,
        Path('backend/tests/test_style_batch22_new_links.py'): patch_legacy_test,
    }
    staged, backups = {}, {}
    flags = []
    for rel, fn in patches.items():
        path = root / rel
        if not path.is_file():
            raise RuntimeError(f'Missing baseline file: {rel}')
        source, eol, bom, original, normalized = _read_source(path)
        installed = MARK in source
        flags.append(installed)
        if installed:
            if rel.name == 'style_tag_transform_map_service.py':
                keys = registry_keys(source)
                if len(keys) != 88 or len(set(keys)) != 88:
                    raise RuntimeError('Partially installed Batch23 registry')
            continue
        if enforce_sha and _git_blob_sha(normalized) != BASE[rel]:
            raise RuntimeError(f'Unexpected local changes since 0bb186d: {rel}; nothing modified')
        updated = fn(source)
        staged[rel] = _encode(updated, eol, bom)
        backups[rel] = original
    new_flags = []
    for rel, payload in NEW.items():
        src = root / payload
        if not src.is_file():
            raise RuntimeError(f'Missing ZIP payload: {payload}')
        value = src.read_bytes()
        ast.parse(value.decode('utf-8'))
        target = root / rel
        exists = target.exists()
        new_flags.append(exists)
        if exists:
            if not target.is_file() or target.read_bytes() != value:
                raise RuntimeError(f'Existing file differs from the new payload: {rel}')
        else:
            staged[rel] = value
    if (any(flags) or any(new_flags)) and not (all(flags) and all(new_flags)):
        raise RuntimeError('Partial Batch23 installation; no files modified')
    return staged, backups


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.capstone_b23_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(root: Path, check: bool = False, enforce_sha: bool = True):
    staged, backups = prepare(root, enforce_sha=enforce_sha)
    if not staged:
        return 'Batch23 already installed; no files changed.'
    if check:
        return f'Batch23 preflight passed: {len(staged)} files; no files modified.'
    backup_dir = root / '.git' / 'capstone_batch23_backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    for rel, data in backups.items():
        target = backup_dir / rel
        if target.exists() and target.read_bytes() != data:
            raise RuntimeError(f'Backup conflict: {target}')
        if not target.exists():
            _atomic_write(target, data)
    completed = []
    try:
        for rel, data in staged.items():
            _atomic_write(root / rel, data)
            completed.append(rel)
    except Exception:
        for rel in reversed(completed):
            if rel in backups:
                _atomic_write(root / rel, backups[rel])
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    return f'Installed Batch23: {len(completed)} files; break/global safe actions.'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    try:
        print(install(ROOT, check=args.check))
        return 0
    except (RuntimeError, OSError, ValueError, UnicodeError, SyntaxError) as exc:
        print(f'Batch23 installation stopped: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
