"""Batch27 guarded transformations, based on installed Batch26 (92 linked tags).

From capstone_main root:
    python backend/tools/install_batch27.py --check
    python backend/tools/install_batch27.py

Preflights exact Batch26 Git-blob fingerprints before writing, verifies each
ZIP payload SHA256, rejects partial installations, preserves CRLF/BOM, and
backs up existing files under .git/capstone_batch27_backups.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = Path('backend/tools/batch27_payload')
MARK = 'CAPSTONE_BATCH27_'
BASE = {
    Path('backend/app/services/style_tag_transform_map_service.py'):
        '99afc4e8f30e62445d6ed4637332d2396a347cb4',
    Path('backend/app/services/style_transform_plan_service.py'):
        'f3b1ef89b72be79766d9d4711e48b45bfb10c87d',
    Path('backend/app/services/style_apply_service.py'):
        'b6ed4c8fd6523422a74bda7d981da3cbbd58f721',
    Path('backend/tests/test_style_batch24_new_links.py'):
        'ad70d37a017f60c50cb88980a7f5ddee71a7ae33',
    Path('backend/tests/test_style_batch26_new_links.py'):
        '078fa56975be844c56ea817c1635fc3d63cbf236',
    Path('backend/tests/test_style_unmapped_patterns_batch12_integration.py'):
        '8df097d91065260ebdc362e01e3d70504c010273',
    Path('backend/tests/test_style_unmapped_patterns_batch13_integration.py'):
        'ed968a63f46f5721837159af48565aad2994e1b6',
}
NEW = {
    Path('backend/app/services/improvement/safe_batch27_service.py'):
        PAYLOAD / 'safe_batch27_service.py.source',
    Path('backend/tests/test_style_batch27_new_links.py'):
        PAYLOAD / 'test_style_batch27_new_links.py.source',
    Path('backend/tools/audit_transform_batch27.py'):
        PAYLOAD / 'audit_transform_batch27.py.source',
}
PAYLOAD_SHA256 = {
    'backend/tools/batch27_payload/safe_batch27_service.py.source': '9da9c37e1290f2b52ec641e3684ca965c33da9c5ca06c6525565975f1540a37d',
    'backend/tools/batch27_payload/test_style_batch27_new_links.py.source': '88445f9bf5c1a32cf669dd3b364c80733f9f63e13e6b15f04992b47483066b33',
    'backend/tools/batch27_payload/audit_transform_batch27.py.source': '6309731aa2c057e49724d7f9ab8f059e691af5be872d18fcabc34ce672e61c05',
}


def once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly one anchor, found {count}')
    return source.replace(old, new, 1)


def registry_keys(source: str) -> list[str]:
    tree = ast.parse(source)
    matches = [node.value for node in tree.body
               if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
               and node.target.id == 'CREATE_ACTION_BY_TAG']
    if len(matches) != 1 or not isinstance(matches[0], ast.Dict):
        raise RuntimeError('Unexpected CREATE_ACTION_BY_TAG format')
    return [key.value for key in matches[0].keys if isinstance(key, ast.Constant)]


def patch_registry(source: str) -> str:
    anchor = 'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
    addition = (
        '    # CAPSTONE_BATCH27_REGISTRY_V1: guarded read-only file I/O and procedural style.\n'
        '    "open 사용": "create_safe_module_io_open",\n'
        '    "파일 입출력 구조": "create_safe_file_io_with",\n'
        '    "절차형 코드 스타일": "create_safe_literal_procedural",\n'
    )
    result = once(source, anchor, anchor + addition, 'registry')
    names = registry_keys(result)
    if len(names) != 95 or len(set(names)) != 95:
        raise RuntimeError('Registry must contain 95 unique linked tags')
    return result


def patch_plan(source: str) -> str:
    anchor = '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n'
    block = '''    # CAPSTONE_BATCH27_METRIC_GATE_V1: both saved tag and prior metric evidence.
    # Two different io.open syntaxes have distinct transformers; both are read-only.
    saved_b27 = _get_style_metrics(diff)
    target_b27 = _get_target_metrics(diff)
    syntax_b27 = _get_tag_names(diff, "style_syntax_names")
    concepts_b27 = _get_tag_names(diff, "style_concept_names")
    if ("open 사용" in syntax_b27
            and _metric_count(saved_b27, "open_call_count") > 0
            and _metric_count(target_b27, "open_call_count") == 0
            and all(_metric_count(target_b27, key) > 0
                    for key in ("import_count", "attribute_count", "call_count"))):
        actions.append({
            "tag": "open 사용",
            "action": "create_safe_module_io_open",
            "reason": "저장 스타일의 open 호출 선호와 단순 io.open 대입문을 확인한 뒤 읽기 전용 파일 접근 형태만 변환합니다.",
        })
    if ("파일 입출력 구조" in concepts_b27
            and _metric_count(saved_b27, "open_call_count") > 0
            and _metric_count(target_b27, "open_call_count") == 0
            and all(_metric_count(target_b27, key) > 0
                    for key in ("import_count", "attribute_count", "call_count"))):
        actions.append({
            "tag": "파일 입출력 구조",
            "action": "create_safe_file_io_with",
            "reason": "파일 입출력 개념 태그가 저장된 경우 단일 io.open 컨텍스트 매니저의 읽기 전용 호출만 변경합니다.",
        })
    if ("절차형 코드 스타일" in concepts_b27
            and "function_count" in saved_b27
            and _metric_count(saved_b27, "function_count") == 0
            and _metric_count(saved_b27, "class_count") == 0
            and _metric_count(target_b27, "function_count") > 0
            and _metric_count(target_b27, "call_count") > 0
            and _metric_count(target_b27, "class_count") == 0):
        actions.append({
            "tag": "절차형 코드 스타일",
            "action": "create_safe_literal_procedural",
            "reason": "저장 스타일이 절차형이고 단독 스크립트의 미사용 private 출력 함수만 안전하게 펼칩니다.",
        })

'''
    source = once(source, anchor, block + anchor, 'plan metrics')
    old = ('        if action is None:\n'
           '            compare_only.append(tag_name)\n'
           '            continue\n')
    new = (
        '        # CAPSTONE_BATCH27_METRIC_ONLY_V1: missing tags alone cannot select these actions.\n'
        '        if tag_name in {"open 사용", "파일 입출력 구조", "절차형 코드 스타일"}:\n'
        '            continue\n'
    )
    return once(source, old, old + new, 'plan missing-tag selection')


def patch_dispatch(source: str) -> str:
    anchor = 'def _get_transform_function(action: str):\n'
    block = (
        '# CAPSTONE_BATCH27_DISPATCH_IMPORT_V1\n'
        'from app.services.improvement.safe_batch27_service import (\n'
        '    transform_safe_module_io_open,\n'
        '    transform_safe_file_io_with,\n'
        '    transform_literal_private_main_to_procedure,\n'
        ')\n\n'
    )
    source = once(source, anchor, block + anchor, 'dispatcher imports')
    marker = '        # CAPSTONE_BATCH26_DISPATCH_MAP_V1\n'
    registry = (
        '        # CAPSTONE_BATCH27_DISPATCH_MAP_V1\n'
        '        "create_safe_module_io_open": transform_safe_module_io_open,\n'
        '        "create_safe_file_io_with": transform_safe_file_io_with,\n'
        '        "create_safe_literal_procedural": transform_literal_private_main_to_procedure,\n'
    )
    return once(source, marker, registry + marker, 'dispatcher mapping')


def patch_test24(source: str) -> str:
    old = "        for tag in ('await 사용', '파일 입출력 구조', '기본 매개변수'):\n"
    new = "        # CAPSTONE_BATCH27_LEGACY_STATUS_V1: file I/O is now narrowly linked.\n        for tag in ('await 사용', '기본 매개변수'):\n"
    return once(source, old, new, 'Batch24 old unsafe tag expectations')


def patch_test26(source: str) -> str:
    old = ('        self.assertEqual(len(CREATE_ACTION_BY_TAG), 92)\n'
           '        self.assertEqual(len(COMPARE_ONLY_TAGS), 10)\n')
    new = ('        # CAPSTONE_BATCH27_LEGACY_COUNT_V1: allow later linked tags.\n'
           '        self.assertGreaterEqual(len(CREATE_ACTION_BY_TAG), 92)\n'
           '        self.assertLessEqual(len(COMPARE_ONLY_TAGS), 10)\n'
           '        self.assertEqual(len(CREATE_ACTION_BY_TAG) + len(COMPARE_ONLY_TAGS), 102)\n')
    source = once(source, old, new, 'Batch26 old fixed counts')
    return once(source,
                "        self.assertIn('파일 입출력 구조', COMPARE_ONLY_TAGS)\n",
                "        self.assertNotIn('파일 입출력 구조', COMPARE_ONLY_TAGS)\n",
                'Batch26 old file I/O compare-only assertion')


def patch_test12(source: str) -> str:
    old = "        for tag in ('await 사용', '파일 입출력 구조'):\n"
    new = (
        '        # CAPSTONE_BATCH27_LEGACY_FILE_IO_V1: only await remains compare-only.\n'
        "        self.assertEqual(get_tag_transform_status('파일 입출력 구조'), 'linked')\n"
        "        for tag in ('await 사용',):\n"
    )
    return once(source, old, new, 'Batch12 compare-only legacy test')


def patch_test13(source: str) -> str:
    old = "        for tag in ('await 사용', '파일 입출력 구조'):\n"
    new = (
        '        # CAPSTONE_BATCH27_LEGACY_FILE_IO_V1: only await remains compare-only.\n'
        "        self.assertEqual(mapping.get_tag_transform_status('파일 입출력 구조'), 'linked')\n"
        "        for tag in ('await 사용',):\n"
    )
    return once(source, old, new, 'Batch13 compare-only legacy test')


PATCHES = {
    Path('backend/app/services/style_tag_transform_map_service.py'): patch_registry,
    Path('backend/app/services/style_transform_plan_service.py'): patch_plan,
    Path('backend/app/services/style_apply_service.py'): patch_dispatch,
    Path('backend/tests/test_style_batch24_new_links.py'): patch_test24,
    Path('backend/tests/test_style_batch26_new_links.py'): patch_test26,
    Path('backend/tests/test_style_unmapped_patterns_batch12_integration.py'): patch_test12,
    Path('backend/tests/test_style_unmapped_patterns_batch13_integration.py'): patch_test13,
}


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def read_file(path: Path):
    raw = path.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    body = raw[3:] if bom else raw
    if b'\r\n' in body and b'\n' in body.replace(b'\r\n', b''):
        raise RuntimeError(f'Mixed newlines in {path}')
    eol = '\r\n' if b'\r\n' in body else '\n'
    return body.replace(b'\r\n', b'\n').decode('utf-8'), eol, bom, raw


def encode_file(source: str, eol: str, bom: bool) -> bytes:
    return (b'\xef\xbb\xbf' if bom else b'') + source.replace('\n', eol).encode('utf-8')


def prepare(root: Path, enforce_sha: bool = True):
    if not (root / '.git').is_dir():
        raise RuntimeError('Run from capstone_main Git root')
    staged: dict[Path, bytes] = {}
    originals: dict[Path, bytes] = {}
    processed_flags = []
    for rel, patch in PATCHES.items():
        path = root / rel
        if not path.is_file():
            raise RuntimeError(f'Missing baseline file: {rel}')
        source, eol, bom, original = read_file(path)
        has_mark = MARK in source
        processed_flags.append(has_mark)
        if has_mark:
            if rel.name == 'style_tag_transform_map_service.py':
                names = registry_keys(source)
                if len(names) != 95 or len(set(names)) != 95:
                    raise RuntimeError('Partial Batch27 tag registry found')
            continue
        if enforce_sha and git_blob(source.encode('utf-8')) != BASE[rel]:
            raise RuntimeError(f'Unexpected local file or wrong baseline: {rel}; no changes made')
        output = patch(source)
        ast.parse(output)
        staged[rel] = encode_file(output, eol, bom)
        originals[rel] = original
    created_flags = []
    for rel, payload_rel in NEW.items():
        path = root / payload_rel
        if not path.is_file():
            raise RuntimeError(f'Missing ZIP payload: {payload_rel}')
        contents = path.read_bytes()
        checksum = PAYLOAD_SHA256[payload_rel.as_posix()]
        if hashlib.sha256(contents).hexdigest() != checksum:
            raise RuntimeError(f'Invalid ZIP payload SHA256: {payload_rel}')
        ast.parse(contents.decode('utf-8'))
        target = root / rel
        exists = target.exists()
        created_flags.append(exists)
        if exists:
            if not target.is_file() or target.read_bytes() != contents:
                raise RuntimeError(f'Conflicting new file at {rel}')
        else:
            staged[rel] = contents
    if (any(processed_flags) or any(created_flags)) and not (
        all(processed_flags) and all(created_flags)
    ):
        raise RuntimeError('Partial Batch27 installation detected; no files were changed')
    return staged, originals


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.capstone_b27_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def install(root: Path, check: bool = False, enforce_sha: bool = True) -> str:
    staged, originals = prepare(root, enforce_sha=enforce_sha)
    if not staged:
        return 'Batch27 already installed; no changes.'
    if check:
        return f'Batch27 preflight passed: {len(staged)} files; no files changed.'
    backup_root = root / '.git' / 'capstone_batch27_backups'
    if backup_root.exists():
        raise RuntimeError('Batch27 backups already exist; refusing overwrite')
    backup_root.mkdir(parents=True)
    for rel, raw in originals.items():
        backup = backup_root / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(raw)
    completed = []
    try:
        for rel, contents in staged.items():
            atomic_write(root / rel, contents)
            completed.append(rel)
    except Exception:
        for rel in reversed(completed):
            if rel in originals:
                atomic_write(root / rel, originals[rel])
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    return f'Installed Batch27: {len(staged)} files; read-only open and procedural style.'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(install(ROOT, check=args.check))
        return 0
    except (RuntimeError, OSError, ValueError, UnicodeError, SyntaxError) as exc:
        print(f'Batch27 installation stopped: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
