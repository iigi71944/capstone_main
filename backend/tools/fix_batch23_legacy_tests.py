"""Batch 23 regression-test expectation correction.

Only changes two obsolete compare-only assertions. Does NOT touch runtime
transformations, tag registry, audit rules, or frontend.

Run from project root:
  python backend/tools/fix_batch23_legacy_tests.py --check
  python backend/tools/fix_batch23_legacy_tests.py

Backups: .git/capstone_batch23_legacy_test_backups/
"""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TARGETS = (
    Path('backend/tests/test_style_unmapped_patterns_batch12_integration.py'),
    Path('backend/tests/test_style_unmapped_patterns_batch13_integration.py'),
)
REGISTRY = Path('backend/app/services/style_tag_transform_map_service.py')
OLD = "        for tag in ('await 사용', '전역 변수 사용', '파일 입출력 구조'):"
NEW = "        for tag in ('await 사용', '파일 입출력 구조'):"
MARK = 'CAPSTONE_BATCH23_LEGACY_TEST_FIX_V1'


def _read(path: Path) -> tuple[str, str, bool]:
    raw = path.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    source = raw.decode('utf-8-sig')
    eol = '\r\n' if b'\r\n' in raw else '\n'
    if '\r\n' in source and '\n' in source.replace('\r\n', ''):
        raise RuntimeError(f'Mixed line endings, stop: {path}')
    return source.replace('\r\n', '\n'), eol, bom


def _encode(source: str, eol: str, bom: bool) -> bytes:
    data = source.replace('\n', eol).encode('utf-8')
    return (b'\xef\xbb\xbf' + data) if bom else data


def _safe_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.capstone_b23_fix_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _patch(source: str, filename: str) -> str:
    if MARK in source:
        if (OLD in source or NEW not in source or
                "'create_safe_readonly_global'" not in source):
            raise RuntimeError(f'Incomplete earlier fix: {filename}')
        return source
    if source.count(OLD) != 1:
        raise RuntimeError(f'Expected exactly one old test assertion: {filename}')
    if NEW in source:
        raise RuntimeError(f'Conflicting partially changed test: {filename}')

    if filename.endswith('batch12_integration.py'):
        predicate = 'get_tag_transform_status'
        action = 'get_create_action_for_tag'
    elif filename.endswith('batch13_integration.py'):
        predicate = 'mapping.get_tag_transform_status'
        action = 'mapping.get_create_action_for_tag'
    else:
        raise RuntimeError(f'Unexpected target: {filename}')
    change = (
        f'        # {MARK}\n'
        f"        self.assertEqual({predicate}('전역 변수 사용'), 'linked')\n"
        f"        self.assertEqual({action}('전역 변수 사용'), 'create_safe_readonly_global')\n"
        + NEW
    )
    updated = source.replace(OLD, change)
    ast.parse(updated)
    return updated


def prepare(root: Path) -> tuple[dict[Path, bytes], dict[Path, bytes]]:
    registry_source, _, _ = _read(root / REGISTRY)
    if ('# CAPSTONE_BATCH23_REGISTRY_V1' not in registry_source or
            '"전역 변수 사용": "create_safe_readonly_global"' not in registry_source or
            '"break문": "create_safe_counted_break"' not in registry_source):
        raise RuntimeError('23차 변환 기능이 적용된 상태가 아닙니다. 설치 상태를 확인해 주세요.')

    originals: dict[Path, bytes] = {}
    updates: dict[Path, bytes] = {}
    for rel in TARGETS:
        absolute = root / rel
        original = absolute.read_bytes()
        source, eol, bom = _read(absolute)
        updated = _patch(source, rel.name)
        originals[rel] = original
        if updated != source:
            updates[rel] = _encode(updated, eol, bom)
    if len(updates) not in (0, 2):
        raise RuntimeError('부분 수정 상태가 감지되었습니다. 원본 파일을 확인해 주세요.')
    return originals, updates


def install(root: Path, check: bool = False) -> str:
    originals, updates = prepare(root)
    if not updates:
        return '23차 레거시 테스트 정정이 이미 적용되어 있습니다. 추가 수정 없음.'
    if check:
        return f'사전 검사 통과: 테스트 파일 {len(updates)}개 수정 예정. 실제 파일은 변경하지 않았습니다.'

    backups = root / '.git' / 'capstone_batch23_legacy_test_backups'
    if not (root / '.git').is_dir():
        raise RuntimeError('프로젝트의 .git 폴더가 없어 설치를 중단합니다.')
    # All checks complete before writing backups/targets.
    for rel in TARGETS:
        backup = backups / rel
        if backup.exists() and backup.read_bytes() != originals[rel]:
            raise RuntimeError(f'기존 백업이 다른 내용을 담고 있습니다: {backup}')
    for rel in TARGETS:
        backup = backups / rel
        if not backup.exists():
            _safe_write(backup, originals[rel])
    completed: list[Path] = []
    try:
        for rel in TARGETS:
            _safe_write(root / rel, updates[rel])
            completed.append(rel)
    except Exception:
        for rel in completed:
            _safe_write(root / rel, originals[rel])
        raise
    return f'23차 레거시 테스트 정정 완료: {len(completed)}개 파일. 백업: {backups}'


def main() -> int:
    parser = argparse.ArgumentParser(description='Fix stale Batch 12/13 tag expectations after Batch 23.')
    parser.add_argument('--check', action='store_true', help='사전 검사만 수행')
    opts = parser.parse_args()
    try:
        print(install(ROOT, check=opts.check))
        return 0
    except (RuntimeError, OSError, UnicodeError, SyntaxError, ValueError) as exc:
        print(f'23차 테스트 정정 중단: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
