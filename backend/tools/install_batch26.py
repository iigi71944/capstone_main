"""Install Batch 26 on Batch24 GitHub commit f559b62 + optional local Batch25.

From the capstone_main repository root:
    python backend/tools/install_batch26.py --check
    python backend/tools/install_batch26.py

Batch25 changes are to independent files and are not overwritten.
All existing files are SHA-checked before any write, backed up under .git,
and restored on a partial failure. Reinstallation is idempotent.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = Path('backend/tools/batch26_payload')
MARK = 'CAPSTONE_BATCH26_'
BASE = {
    Path('backend/app/services/style_tag_transform_map_service.py'):
        '816cf62c57f331de6a041e4d89060782491a9d9f',
    Path('backend/app/services/style_transform_plan_service.py'):
        '8fe689bbd86cd4b6cfa36f01661cea195dbccf75',
    Path('backend/app/services/style_apply_service.py'):
        '4f23631a8ec11d8d89275d7789935734c6760f8b',
    Path('backend/tests/test_style_batch24_new_links.py'):
        'f869ccdce74d41e6e2b8ec4cafb58f2a9929c980',
}
NEW = {
    Path('backend/app/services/improvement/safe_batch26_service.py'):
        PAYLOAD / 'safe_batch26_service.py.source',
    Path('backend/tests/test_style_batch26_new_links.py'):
        PAYLOAD / 'test_style_batch26_new_links.py.source',
    Path('backend/tools/audit_transform_batch26.py'):
        PAYLOAD / 'audit_transform_batch26.py.source',
}
# Set during package construction, never downloaded at runtime.
PAYLOAD_SHA256 = {
    'backend/tools/batch26_payload/safe_batch26_service.py.source': 'c30f989a702c7f4687d7a73b5545b9f1e1977816ebb57ffe6e5738ac179ae9d7',
    'backend/tools/batch26_payload/test_style_batch26_new_links.py.source': '6eead6fbc48bbddd7b1330c7d3503c0f71741f841b1d8fdcca11f12a706f184d',
    'backend/tools/batch26_payload/audit_transform_batch26.py.source': 'd94ca1234dba3d4c2c4421fd4bc17fac0af27c6cd40b83d719c30015c71b8bc4',
}


def once(text: str, before: str, after: str, description: str) -> str:
    n = text.count(before)
    if n != 1:
        raise RuntimeError(f'{description}: expected one anchor, got {n}')
    return text.replace(before, after, 1)


def registry_keys(source: str) -> list[str]:
    tree = ast.parse(source)
    found = [node.value for node in tree.body
             if isinstance(node, ast.AnnAssign)
             and isinstance(node.target, ast.Name)
             and node.target.id == 'CREATE_ACTION_BY_TAG']
    if len(found) != 1 or not isinstance(found[0], ast.Dict):
        raise RuntimeError('Cannot locate tag registry')
    return [key.value for key in found[0].keys if isinstance(key, ast.Constant)]


def patch_registry(source: str) -> str:
    anchor = 'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
    addition = (
        '    # CAPSTONE_BATCH26_REGISTRY_V1: concept-driven nested input/global styles.\n'
        '    "사용자 입력 처리 구조": "create_safe_nested_input_structure",\n'
        '    "전역 상태 의존 구조": "create_safe_global_calculation",\n'
    )
    result = once(source, anchor, anchor + addition, 'tag registry')
    keys = registry_keys(result)
    if len(keys) != 92 or len(set(keys)) != 92:
        raise RuntimeError('Expected 92 unique linked tags after Batch26')
    return result


def patch_plan(source: str) -> str:
    anchor = '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n'
    block = '''    # CAPSTONE_BATCH26_METRIC_GATE_V1: concept tag AND recorded metrics required.
    # Batch21/23 handle simpler patterns; these two actions extend coverage.
    saved_b26 = _get_style_metrics(diff)
    target_b26 = _get_target_metrics(diff)
    concepts_b26 = _get_tag_names(diff, "style_concept_names")
    if ("사용자 입력 처리 구조" in concepts_b26
            and _metric_count(saved_b26, "input_call_count") > 0
            and _metric_count(target_b26, "input_call_count") == 0
            and all(_metric_count(target_b26, key) > 0
                    for key in ("import_count", "attribute_count", "call_count"))
            and not any(a.get("action") == "create_safe_nested_input_structure"
                        for a in actions)):
        actions.append({
            "tag": "사용자 입력 처리 구조",
            "action": "create_safe_nested_input_structure",
            "reason": "저장 스타일에 입력 처리 개념이 있고, 중첩된 builtins.input 호출이 안전한 형태일 때만 정리합니다.",
        })
    if ("전역 상태 의존 구조" in concepts_b26
            and _metric_count(saved_b26, "global_count") > 0
            and _metric_count(target_b26, "global_count") == 0
            and _metric_count(target_b26, "function_count") > 0
            and _metric_count(target_b26, "assign_count") > 0
            and not any(a.get("action") == "create_safe_global_calculation"
                        for a in actions)):
        actions.append({
            "tag": "전역 상태 의존 구조",
            "action": "create_safe_global_calculation",
            "reason": "저장 스타일에 전역 상태 개념이 있고, 상수 전역값을 읽는 단순 계산 함수에만 명시적 global을 적용합니다.",
        })

'''
    result = once(source, anchor, block + anchor, 'metric gate')
    skip_anchor = ('        if action is None:\n'
                   '            compare_only.append(tag_name)\n'
                   '            continue\n')
    skip_block = (
        '        # CAPSTONE_BATCH26_METRIC_ONLY_V1: never transform from tag name alone.\n'
        '        if tag_name in {"사용자 입력 처리 구조", "전역 상태 의존 구조"}:\n'
        '            continue\n'
    )
    return once(result, skip_anchor, skip_anchor + skip_block, 'missing-tag gate')


def patch_dispatch(source: str) -> str:
    anchor = 'def _get_transform_function(action: str):\n'
    imports = (
        '# CAPSTONE_BATCH26_DISPATCH_IMPORT_V1\n'
        'from app.services.improvement.safe_batch26_service import (\n'
        '    transform_nested_builtin_input_structure,\n'
        '    transform_readonly_global_calculation,\n'
        ')\n\n'
    )
    source = once(source, anchor, imports + anchor, 'dispatch imports')
    marker = '        # CAPSTONE_BATCH24_DISPATCH_MAP_V1\n'
    mappings = (
        '        # CAPSTONE_BATCH26_DISPATCH_MAP_V1\n'
        '        "create_safe_nested_input_structure": transform_nested_builtin_input_structure,\n'
        '        "create_safe_global_calculation": transform_readonly_global_calculation,\n'
    )
    return once(source, marker, mappings + marker, 'dispatch actions')


def patch_legacy_test(source: str) -> str:
    before = ('        self.assertEqual(len(CREATE_ACTION_BY_TAG), 90)\n'
              '        self.assertEqual(len(COMPARE_ONLY_TAGS), 12)\n')
    after = (
        '        # CAPSTONE_BATCH26_LEGACY_MINIMUM_V1: later tags extend the registry.\n'
        '        self.assertGreaterEqual(len(CREATE_ACTION_BY_TAG), 90)\n'
        '        self.assertLessEqual(len(COMPARE_ONLY_TAGS), 12)\n'
        '        self.assertEqual(len(CREATE_ACTION_BY_TAG) + len(COMPARE_ONLY_TAGS), 102)\n'
    )
    return once(source, before, after, 'Batch24 legacy count')


PATCHES = {
    Path('backend/app/services/style_tag_transform_map_service.py'): patch_registry,
    Path('backend/app/services/style_transform_plan_service.py'): patch_plan,
    Path('backend/app/services/style_apply_service.py'): patch_dispatch,
    Path('backend/tests/test_style_batch24_new_links.py'): patch_legacy_test,
}


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def read_file(path: Path):
    raw = path.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    data = raw[3:] if bom else raw
    if b'\r\n' in data and b'\n' in data.replace(b'\r\n', b''):
        raise RuntimeError(f'Mixed line endings in {path}')
    eol = '\r\n' if b'\r\n' in data else '\n'
    return data.replace(b'\r\n', b'\n').decode('utf-8'), eol, bom, raw


def encode_file(text: str, eol: str, bom: bool) -> bytes:
    return (b'\xef\xbb\xbf' if bom else b'') + text.replace('\n', eol).encode('utf-8')


def prepare(root: Path, enforce_sha: bool = True):
    if not (root / '.git').is_dir():
        raise RuntimeError('Run the installer from capstone_main Git root')
    staged: dict[Path, bytes] = {}
    originals: dict[Path, bytes] = {}
    patched_flags = []
    for rel, patch in PATCHES.items():
        path = root / rel
        if not path.is_file():
            raise RuntimeError(f'Missing original file: {rel}')
        source, eol, bom, raw = read_file(path)
        already = MARK in source
        patched_flags.append(already)
        if already:
            if rel.name == 'style_tag_transform_map_service.py':
                keys = registry_keys(source)
                if len(keys) != 92 or len(set(keys)) != 92:
                    raise RuntimeError('Partial Batch26 registry')
            continue
        normalized = source.encode('utf-8')
        if enforce_sha and git_blob(normalized) != BASE[rel]:
            raise RuntimeError(f'Unexpected source changes at {rel}; aborting before writes')
        updated = patch(source)
        ast.parse(updated)
        staged[rel] = encode_file(updated, eol, bom)
        originals[rel] = raw
    new_flags = []
    for rel, payload_path in NEW.items():
        source_path = root / payload_path
        if not source_path.is_file():
            raise RuntimeError(f'Missing ZIP payload: {payload_path}')
        data = source_path.read_bytes()
        expected = PAYLOAD_SHA256[payload_path.as_posix()]
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError(f'Payload integrity check failed: {payload_path}')
        ast.parse(data.decode('utf-8'))
        target = root / rel
        exists = target.exists()
        new_flags.append(exists)
        if exists:
            if not target.is_file() or target.read_bytes() != data:
                raise RuntimeError(f'New file already exists with different content: {rel}')
        else:
            staged[rel] = data
    if (any(patched_flags) or any(new_flags)) and not (
        all(patched_flags) and all(new_flags)
    ):
        raise RuntimeError('Partial Batch26 installation detected; nothing changed')
    return staged, originals


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.capstone_batch26_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def install(root: Path, check: bool = False, enforce_sha: bool = True) -> str:
    staged, original = prepare(root, enforce_sha=enforce_sha)
    if not staged:
        return 'Batch26 already installed; no files changed.'
    if check:
        return f'Batch26 preflight OK: {len(staged)} files; no files modified.'
    backup = root / '.git' / 'capstone_batch26_backups'
    if backup.exists():
        raise RuntimeError('Backup folder already exists; refusing overwrite')
    backup.mkdir(parents=True)
    for rel, raw in original.items():
        dest = backup / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    written = []
    try:
        for rel, data in staged.items():
            atomic_write(root / rel, data)
            written.append(rel)
    except Exception:
        for rel in reversed(written):
            if rel in original:
                atomic_write(root / rel, original[rel])
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    return f'Installed Batch26: {len(staged)} files, nested input + global calculation concepts.'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(install(ROOT, check=args.check))
        return 0
    except (RuntimeError, OSError, UnicodeError, SyntaxError, ValueError) as exc:
        print(f'Batch26 installation stopped: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
