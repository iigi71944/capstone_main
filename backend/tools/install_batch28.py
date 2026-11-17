"""Batch28 tag-specific policy metadata and shared-action deduplication.

From capstone_main root (after Batch27, clean Git commit 570aeba):
    python backend/tools/install_batch28.py --check
    python backend/tools/install_batch28.py

- Refuses unexpected source fingerprints, partial installs, modified payloads.
- Preserves Windows CRLF, BOM and existing style/action compatibility.
- Only modifies two backend source files; no frontend or saved style schema.
- Stores original files under .git/capstone_batch28_backups.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = Path('backend/tools/batch28_payload')
MARK = 'CAPSTONE_BATCH28_'
BASE = {
    Path('backend/app/services/style_transform_plan_service.py'):
        '8915a5d9d5cbb8ed59983ef03d636b65c7d22bfa',
    Path('backend/app/services/style_apply_service.py'):
        '3892954b5d7541572d9302a0e49d58477955588f',
}
REGISTRY_BASE = 'ae4a4c9126738ff91c688e50e41dbc9f64bcdb3c'
NEW = {
    Path('backend/app/services/style_tag_action_policy_service.py'):
        PAYLOAD / 'style_tag_action_policy_service.py.source',
    Path('backend/tests/test_style_batch28_tag_policies.py'):
        PAYLOAD / 'test_style_batch28_tag_policies.py.source',
    Path('backend/tools/audit_transform_batch28.py'):
        PAYLOAD / 'audit_transform_batch28.py.source',
}
PAYLOAD_SHA256 = {
    'backend/tools/batch28_payload/audit_transform_batch28.py.source': '7d2901c2e8bbf22c1359fe50abb295f22fd404a9ab1e82b723f3d0a56b422793',
    'backend/tools/batch28_payload/style_tag_action_policy_service.py.source': 'e30e26d37d529d1f823554dd53fd837a0a9f4acf55302b7d9b59546a748758c7',
    'backend/tools/batch28_payload/test_style_batch28_tag_policies.py.source': 'd0c4bfb90e1e95ea00ab5ef96348f121668e3b0940bd1c347646cab4f1f70b84',
}


def once(source: str, before: str, after: str, label: str) -> str:
    count = source.count(before)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly one anchor, got {count}')
    return source.replace(before, after, 1)


def patch_plan(source: str) -> str:
    anchor = 'from app.services.style_tag_transform_map_service import get_create_action_for_tag\n'
    source = once(source, anchor, anchor + (
        'from app.services.style_tag_action_policy_service import finalize_tag_action_policies\n'
        '# CAPSTONE_BATCH28_PLAN_IMPORT_V1\n'
    ), 'plan import')
    before = '''    return {
        "actions": _resolve_new_family_actions(_resolve_iteration_actions(
            _resolve_dictionary_actions(_resolve_collection_actions(actions))
        )),
        "compare_only": sorted(set(compare_only)),
    }
'''
    after = '''    # CAPSTONE_BATCH28_PLAN_FINALIZE_V1: tag-specific policy IDs and shared-engine
    # deduplication only after legacy direction/conflict resolution completes.
    # Public action strings and compare-only semantics are unchanged.
    return {
        "actions": finalize_tag_action_policies(
            _resolve_new_family_actions(_resolve_iteration_actions(
                _resolve_dictionary_actions(_resolve_collection_actions(actions))
            ))
        ),
        "compare_only": sorted(set(compare_only)),
    }
'''
    return once(source, before, after, 'plan finalizer')


def patch_apply(source: str) -> str:
    anchor = '    result = {"tag": tag_name, "action": action, "status": ""}\n'
    replacement = anchor + '''    # CAPSTONE_BATCH28_APPLY_LEDGER_V1: expose independent policy intent while
    # retaining the real, previously tested action and transformer function.
    if isinstance(action_item.get("policy_action"), str):
        for key in ("policy_action", "policy_family", "policy_role", "policy_source_tags"):
            if key in action_item:
                result[key] = action_item[key]
'''
    return once(source, anchor, replacement, 'apply trace metadata')


PATCHES = {
    Path('backend/app/services/style_transform_plan_service.py'): patch_plan,
    Path('backend/app/services/style_apply_service.py'): patch_apply,
}


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def read_file(path: Path):
    original = path.read_bytes()
    bom = original.startswith(b'\xef\xbb\xbf')
    body = original[3:] if bom else original
    if b'\r\n' in body and b'\n' in body.replace(b'\r\n', b''):
        raise RuntimeError(f'{path}: mixed CRLF/LF line endings')
    eol = '\r\n' if b'\r\n' in body else '\n'
    source = body.replace(b'\r\n', b'\n').decode('utf-8')
    return source, eol, bom, original


def encode_file(source: str, eol: str, bom: bool) -> bytes:
    return (b'\xef\xbb\xbf' if bom else b'') + source.replace('\n', eol).encode('utf-8')


def _verify_registry(root: Path, enforce_sha: bool):
    rel = Path('backend/app/services/style_tag_transform_map_service.py')
    path = root / rel
    if not path.is_file():
        raise RuntimeError('Missing tag registry')
    source, _, _, _ = read_file(path)
    if enforce_sha and git_blob(source.encode('utf-8')) != REGISTRY_BASE:
        raise RuntimeError(f'Unexpected tag registry at {rel} (expected Batch27)')
    module = ast.parse(source)
    values = [node.value for node in module.body
              if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
              and node.target.id == 'CREATE_ACTION_BY_TAG']
    if len(values) != 1 or not isinstance(values[0], ast.Dict):
        raise RuntimeError('Unexpected tag registry format')
    names = [key.value for key in values[0].keys if isinstance(key, ast.Constant)]
    if len(names) != 95 or len(set(names)) != 95:
        raise RuntimeError('Tag registry must contain 95 unique entries')


def prepare(root: Path, enforce_sha: bool = True):
    if not (root / '.git').is_dir():
        raise RuntimeError('Run installer in capstone_main Git project')
    _verify_registry(root, enforce_sha)
    staged: dict[Path, bytes] = {}
    originals: dict[Path, bytes] = {}
    processed_flags = []
    for rel, patch in PATCHES.items():
        path = root / rel
        if not path.is_file():
            raise RuntimeError(f'Missing baseline file: {rel}')
        source, eol, bom, original = read_file(path)
        marked = MARK in source
        processed_flags.append(marked)
        if marked:
            if 'CAPSTONE_BATCH28_' not in source:
                raise RuntimeError(f'Unexpected install marker at {rel}')
            continue
        if enforce_sha and git_blob(source.encode('utf-8')) != BASE[rel]:
            raise RuntimeError(f'Unexpected local file or wrong baseline: {rel}; no files changed')
        output = patch(source)
        ast.parse(output)
        originals[rel] = original
        staged[rel] = encode_file(output, eol, bom)
    created_flags = []
    for rel, payload_rel in NEW.items():
        payload = root / payload_rel
        if not payload.is_file():
            raise RuntimeError(f'Missing ZIP payload: {payload_rel}')
        contents = payload.read_bytes()
        expected = PAYLOAD_SHA256[payload_rel.as_posix()]
        if hashlib.sha256(contents).hexdigest() != expected:
            raise RuntimeError(f'Invalid ZIP payload checksum: {payload_rel}')
        ast.parse(contents.decode('utf-8'))
        target = root / rel
        exists = target.exists()
        created_flags.append(exists)
        if exists:
            if not target.is_file() or target.read_bytes() != contents:
                raise RuntimeError(f'Conflicting new file: {rel}')
        else:
            staged[rel] = contents
    if (any(processed_flags) or any(created_flags)) and not (
            all(processed_flags) and all(created_flags)):
        raise RuntimeError('Partial Batch28 installation detected; no files changed')
    return staged, originals


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.capstone_b28_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def install(root: Path, check: bool = False, enforce_sha: bool = True) -> str:
    staged, originals = prepare(root, enforce_sha=enforce_sha)
    if not staged:
        return 'Batch28 already installed; no changes.'
    if check:
        return f'Batch28 preflight passed: {len(staged)} files; no changes.'
    backup_root = root / '.git' / 'capstone_batch28_backups'
    if backup_root.exists():
        raise RuntimeError('Batch28 backup folder already exists; refusing overwrite')
    backup_root.mkdir(parents=True)
    for rel, raw in originals.items():
        backup = backup_root / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(raw)
    completed = []
    try:
        for rel, data in staged.items():
            atomic_write(root / rel, data)
            completed.append(rel)
    except Exception:
        for rel in reversed(completed):
            if rel in originals:
                atomic_write(root / rel, originals[rel])
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    return f'Installed Batch28: {len(staged)} backend files; 16 shared groups / 32 tag policies.'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(install(ROOT, check=args.check))
        return 0
    except (RuntimeError, OSError, ValueError, UnicodeError, SyntaxError, KeyError) as exc:
        print(f'Batch28 installation stopped: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
