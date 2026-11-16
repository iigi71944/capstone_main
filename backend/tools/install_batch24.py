"""Install Batch24 onto clean GitHub 23rd-batch commit 4b2e506.

Run at capstone_main repo root:
    python backend/tools/install_batch24.py --check
    python backend/tools/install_batch24.py

Preflight checks all original blob SHAs and all packaged payloads before write.
Files are written atomically and rolled back on error; originals are backed up
under .git/capstone_batch24_backups.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = Path('backend/tools/batch24_payload')
MARK = 'CAPSTONE_BATCH24_'
PATCHES = {
    Path('backend/app/services/style_tag_transform_map_service.py'): 'registry',
    Path('backend/app/services/style_transform_plan_service.py'): 'plan',
    Path('backend/app/services/style_apply_service.py'): 'dispatch',
    Path('backend/tests/test_style_batch23_new_links.py'): 'legacy',
}
NEW = {
    Path('backend/app/services/improvement/safe_batch24_service.py'):
        PAYLOAD / 'safe_batch24_service.py.source',
    Path('backend/tests/test_style_batch24_new_links.py'):
        PAYLOAD / 'test_style_batch24_new_links.py.source',
    Path('backend/tools/audit_transform_batch24.py'):
        PAYLOAD / 'audit_transform_batch24.py.source',
}
EXPECTED_GIT_BLOBS = {
    Path('backend/app/services/style_tag_transform_map_service.py'):
        '2103d5dcb9dd3e86779e5f41d72855301b8ccf8d',
    Path('backend/app/services/style_transform_plan_service.py'):
        'a99e1258d69111fa4f6b7a825b770ad0cf5857dc',
    Path('backend/app/services/style_apply_service.py'):
        'a08632ffe38058dd987416fb124a504f59df8bc0',
    Path('backend/tests/test_style_batch23_new_links.py'):
        '47639b702b402a4ef66ccc8488eab42acbbd7cf5',
}
PAYLOAD_SHA256 = {
    'backend/tools/batch24_payload/safe_batch24_service.py.source': 'e60e15ab07440fa278a37a884cb9992d2c1244f2e4f060d1acca27134cf285a1',
    'backend/tools/batch24_payload/test_style_batch24_new_links.py.source': '778501478f5eada6f1b3b84780adc7be9263601590211b17619a5eba970f2474',
    'backend/tools/batch24_payload/audit_transform_batch24.py.source': 'f72e56d242f88babf32f2f86d142cfe1c094f9c2ce71e390df2567b61e2b2d60',
}


def _replace_once(source, before, after, name):
    if source.count(before) != 1:
        raise RuntimeError(f'{name}: expected exactly one source anchor, got {source.count(before)}')
    return source.replace(before, after, 1)


def _registry_keys(source):
    tree = ast.parse(source)
    matches = [stmt.value for stmt in tree.body
               if isinstance(stmt, ast.AnnAssign)
               and isinstance(stmt.target, ast.Name)
               and stmt.target.id == 'CREATE_ACTION_BY_TAG']
    if len(matches) != 1 or not isinstance(matches[0], ast.Dict):
        raise RuntimeError('Unexpected CREATE_ACTION_BY_TAG declaration')
    return [key.value for key in matches[0].keys if isinstance(key, ast.Constant)]


def patch_registry(source):
    before = 'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
    after = before + (
        '    # CAPSTONE_BATCH24_REGISTRY_V1: constrained builtin I/O styles.\n'
        '    "import문": "create_safe_explicit_builtins_import",\n'
        '    "입출력 중심 코드": "create_safe_literal_print_merge",\n'
    )
    changed = _replace_once(source, before, after, 'registry')
    keys = _registry_keys(changed)
    if len(keys) != 90 or len(set(keys)) != 90:
        raise RuntimeError('Batch24 registry must have 90 distinct keys')
    return changed


def patch_plan(source):
    before = '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n'
    block = '''    # CAPSTONE_BATCH24_METRIC_GATE_V1: never select from a tag name alone.
    # A stored print-argument preference and a stored explicit-import preference
    # allow only narrowly recognized top-level print statements to change.
    saved_b24 = _get_style_metrics(diff)
    target_b24 = _get_target_metrics(diff)
    if (_metric_count(saved_b24, "print_call_count") > 0
            and _metric_count(target_b24, "print_call_count") > 0
            and _metric_count(saved_b24, "string_literal_count") > 0
            and 0 < _metric_count(saved_b24, "positional_arg_count")
            < _metric_count(target_b24, "positional_arg_count")):
        actions.append({
            "tag": "입출력 중심 코드",
            "action": "create_safe_literal_print_merge",
            "reason": "저장된 출력 인자 선호가 확인된 경우 상수 문자열 print 인자만 합칩니다.",
        })
    if (_metric_count(saved_b24, "import_count") > 0
            and _metric_count(target_b24, "import_count") == 0
            and _metric_count(target_b24, "print_call_count") > 0):
        actions.append({
            "tag": "import문",
            "action": "create_safe_explicit_builtins_import",
            "reason": "저장된 import 사용 선호에 따라 단순 print 전용 코드에 builtins import를 명시합니다.",
        })

'''
    source = _replace_once(source, before, block + before, 'plan metrics')
    previous = '        # CAPSTONE_BATCH23_METRIC_ONLY_V1: do not generate from absent tags.\n'
    # Version 23 has a skip rule for its own tag family; add the new skip after
    # the first tag= get_create_action occurrence, not before the metadata check.
    anchor = '        if action is None:\n            compare_only.append(tag_name)\n            continue\n'
    source = _replace_once(source, anchor, anchor + (
        '        # CAPSTONE_BATCH24_METRIC_ONLY_V1: the metrics above are mandatory.\n'
        '        if tag_name in {"import문", "입출력 중심 코드"}:\n'
        '            continue\n'
    ), 'plan tag gate')
    return source


def patch_dispatch(source):
    anchor = 'def _get_transform_function(action: str):\n'
    source = _replace_once(source, anchor, (
        '# CAPSTONE_BATCH24_DISPATCH_IMPORT_V1\n'
        'from app.services.improvement.safe_batch24_service import (\n'
        '    transform_simple_print_to_explicit_builtins_import,\n'
        '    transform_simple_literal_print_arguments,\n'
        ')\n\n'
    ) + anchor, 'dispatch import')
    map_anchor = '        # CAPSTONE_BATCH23_DISPATCH_MAP_V1\n'
    source = _replace_once(source, map_anchor, (
        '        # CAPSTONE_BATCH24_DISPATCH_MAP_V1\n'
        '        "create_safe_explicit_builtins_import": transform_simple_print_to_explicit_builtins_import,\n'
        '        "create_safe_literal_print_merge": transform_simple_literal_print_arguments,\n'
    ) + map_anchor, 'dispatch mapping')
    return source


def patch_legacy(source):
    before = (
        '        self.assertEqual(len(CREATE_ACTION_BY_TAG), 88)\n'
        '        self.assertEqual(len(COMPARE_ONLY_TAGS), 14)\n'
    )
    after = (
        '        # CAPSTONE_BATCH24_LEGACY_COUNT_V1: preserve the batch23 minimum.\n'
        '        self.assertGreaterEqual(len(CREATE_ACTION_BY_TAG), 88)\n'
        '        self.assertLessEqual(len(COMPARE_ONLY_TAGS), 14)\n'
        '        self.assertEqual(len(CREATE_ACTION_BY_TAG) + len(COMPARE_ONLY_TAGS), 102)\n'
    )
    return _replace_once(source, before, after, 'batch23 legacy test')


PATCH_FN = {'registry': patch_registry, 'plan': patch_plan,
            'dispatch': patch_dispatch, 'legacy': patch_legacy}


def _git_sha(content):
    return hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()


def _read(path):
    raw = path.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    stripped = raw[3:] if bom else raw
    if b'\r\n' in stripped and b'\n' in stripped.replace(b'\r\n', b''):
        raise RuntimeError(f'Mixed line endings: {path}')
    eol = '\r\n' if b'\r\n' in stripped else '\n'
    normalized = stripped.replace(b'\r\n', b'\n')
    return normalized.decode('utf-8'), eol, bom, raw, normalized


def _encode(source, eol, bom):
    return (b'\xef\xbb\xbf' if bom else b'') + source.replace('\n', eol).encode('utf-8')


def prepare(root):
    if not (root / '.git').is_dir():
        raise RuntimeError('Run from the capstone_main Git repository root')
    staged = {}
    backups = {}
    already = []
    for rel, kind in PATCHES.items():
        path = root / rel
        if not path.is_file():
            raise RuntimeError(f'Missing tracked source: {rel}')
        source, eol, bom, original, normalized = _read(path)
        installed = MARK in source
        already.append(installed)
        if installed:
            if rel.name == 'style_tag_transform_map_service.py':
                keys = _registry_keys(source)
                if len(keys) != 90 or len(set(keys)) != 90:
                    raise RuntimeError('Partial/invalid Batch24 registry')
            continue
        actual_sha = _git_sha(normalized)
        if actual_sha != EXPECTED_GIT_BLOBS[rel]:
            raise RuntimeError(f'Unexpected local edits or baseline mismatch: {rel} '
                               f'(expected GitHub 4b2e506); nothing modified')
        updated = PATCH_FN[kind](source)
        ast.parse(updated)
        staged[rel] = _encode(updated, eol, bom)
        backups[rel] = original
    new_existed = []
    for rel, payload in NEW.items():
        source_path = root / payload
        if not source_path.is_file():
            raise RuntimeError(f'Missing ZIP payload: {payload}')
        data = source_path.read_bytes()
        expected = PAYLOAD_SHA256.get(str(payload).replace('\\', '/'))
        if not expected or hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError(f'ZIP payload integrity check failed: {payload}')
        ast.parse(data.decode('utf-8'))
        target = root / rel
        exists = target.exists()
        new_existed.append(exists)
        if exists:
            if not target.is_file() or target.read_bytes() != data:
                raise RuntimeError(f'Unexpected existing target: {rel}')
        else:
            staged[rel] = data
    if (any(already) or any(new_existed)) and not (all(already) and all(new_existed)):
        raise RuntimeError('Partial Batch24 installation: nothing was changed')
    return staged, backups


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.capstone_b24_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def install(root, check=False):
    staged, originals = prepare(root)
    if not staged:
        return 'Batch24 already installed; no changes.'
    if check:
        return f'Batch24 preflight passed: {len(staged)} files; no files modified.'
    backup_root = root / '.git' / 'capstone_batch24_backups'
    backup_root.mkdir(parents=True, exist_ok=True)
    for rel, data in originals.items():
        target = backup_root / rel
        if target.exists() and target.read_bytes() != data:
            raise RuntimeError(f'Conflicting backup, not installing: {target}')
        _atomic_write(target, data)
    completed = []
    try:
        for rel, data in staged.items():
            _atomic_write(root / rel, data)
            completed.append(rel)
    except Exception:
        for rel in reversed(completed):
            if rel in originals:
                _atomic_write(root / rel, originals[rel])
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    return f'Installed Batch24: {len(staged)} files (2 new automatic conversions).'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(install(ROOT, check=args.check))
        return 0
    except (RuntimeError, UnicodeError, OSError, SyntaxError, ValueError) as exc:
        print(f'Batch24 installation stopped: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
