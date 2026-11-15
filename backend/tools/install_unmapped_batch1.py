"""Safely install capstone's first previously-unmapped concept transform batch.

This installer targets the GitHub main commit 832f1b4. It checks original Git
blob IDs before patching, makes a rollback backup inside .git, and never
replaces an unknown local version of the two existing production files.

From the repository root:
    python backend/tools/install_unmapped_batch1.py --check
    python backend/tools/install_unmapped_batch1.py
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from datetime import datetime
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile

MARK = 'CAPSTONE_UNMAPPED_BATCH1_V1'
TARGET_COMMIT = '832f1b4'
OLD_BLOB_IDS = {
    'backend/app/services/style_tag_transform_map_service.py': '0116bf09c48ca76caeba456413386c54a6a8eca6',
    'backend/app/services/style_apply_service.py': '796ce3f37f750be6b2b9517e8e376c101b1308f7',
}
ADDED_FILES = {
    'backend/app/services/improvement/safe_unmapped_patterns_service.py': 'safe_unmapped_patterns_service.py.source',
    'backend/tests/test_style_unmapped_patterns_batch1.py': 'test_style_unmapped_patterns_batch1.py.source',
}
PAYLOAD_DIR = Path(__file__).resolve().parent / 'unmapped_batch1_payload'

MAP_ANCHOR = 'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
MAP_INSERT = '''    # CAPSTONE_UNMAPPED_BATCH1_V1: save format unchanged; previously compare-only concepts.
    "조건문 중첩 구조": "create_safe_nested_conditions",
    "깊은 중첩 구조": "create_safe_deep_conditions",
    "데이터 컬렉션 중심 구조": "create_safe_collection_literals",
    "반환 중심 구조": "create_safe_multiple_returns",
'''
SERVICE_ANCHOR = 'def _get_transform_function(action: str):\n'
SERVICE_IMPORT = '''# CAPSTONE_UNMAPPED_BATCH1_V1: new conservative, source-preserving concept actions.
from app.services.improvement.safe_unmapped_patterns_service import (
    transform_to_nested_conditions,
    transform_to_deep_conditions,
    transform_to_literal_collections,
    transform_to_multiple_returns,
)

'''
DISPATCH_ANCHOR = '    action_map = {\n'
DISPATCH_INSERT = '''        # CAPSTONE_UNMAPPED_BATCH1_V1: additional compare-only concept transforms.
        "create_safe_nested_conditions": transform_to_nested_conditions,
        "create_safe_deep_conditions": transform_to_deep_conditions,
        "create_safe_collection_literals": transform_to_literal_collections,
        "create_safe_multiple_returns": transform_to_multiple_returns,
'''


class InstallationError(Exception):
    pass


@dataclass(frozen=True)
class Change:
    path: Path
    new_bytes: bytes
    old_bytes: bytes | None


def _git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()


def _decode(raw: bytes, label: str) -> tuple[str, bool, bool]:
    has_bom = raw.startswith(b'\xef\xbb\xbf')
    source = raw[3:] if has_bom else raw
    try:
        decoded = source.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise InstallationError(label + ': UTF-8 코드가 아닙니다. 설치하지 않았습니다.') from exc
    has_crlf = b'\r\n' in source
    return decoded.replace('\r\n', '\n'), has_bom, has_crlf


def _encode(source: str, *, has_bom: bool, has_crlf: bool) -> bytes:
    normalized = source.replace('\n', '\r\n') if has_crlf else source
    return (b'\xef\xbb\xbf' if has_bom else b'') + normalized.encode('utf-8')


def _replace_once(source: str, anchor: str, replacement: str, label: str) -> str:
    if source.count(anchor) != 1:
        raise InstallationError(label + ': 수정 위치가 예상과 다릅니다. 기존 파일은 변경하지 않습니다.')
    return source.replace(anchor, replacement, 1)


def patch_registry(source: str) -> str:
    if MARK in source:
        if not all(f'"{name}": "{action}"' in source for name, action in (
            ('조건문 중첩 구조', 'create_safe_nested_conditions'),
            ('깊은 중첩 구조', 'create_safe_deep_conditions'),
            ('데이터 컬렉션 중심 구조', 'create_safe_collection_literals'),
            ('반환 중심 구조', 'create_safe_multiple_returns'),
        )):
            raise InstallationError('태그 매핑 파일에 부분 설치 흔적이 있습니다.')
        return source
    updated = _replace_once(source, MAP_ANCHOR, MAP_ANCHOR + MAP_INSERT, '태그 매핑')
    ast.parse(updated)
    return updated


def patch_dispatcher(source: str) -> str:
    if MARK in source:
        required = ('create_safe_nested_conditions', 'create_safe_deep_conditions',
                    'create_safe_collection_literals', 'create_safe_multiple_returns',
                    'transform_to_nested_conditions', 'transform_to_deep_conditions',
                    'transform_to_literal_collections', 'transform_to_multiple_returns')
        if not all(token in source for token in required):
            raise InstallationError('변환 실행 파일에 부분 설치 흔적이 있습니다.')
        return source
    updated = _replace_once(source, SERVICE_ANCHOR, SERVICE_IMPORT + SERVICE_ANCHOR, '변환 실행')
    updated = _replace_once(updated, DISPATCH_ANCHOR, DISPATCH_ANCHOR + DISPATCH_INSERT, '액션 등록')
    ast.parse(updated)
    return updated


def plan(root: Path) -> list[Change]:
    root = Path(root).resolve()
    if not (root / '.git').exists() or not (root / 'docker-compose.yml').is_file():
        raise InstallationError('capstone_main Git 프로젝트 최상위 폴더에서 실행해 주세요.')
    changes: list[Change] = []
    for relative, sha in OLD_BLOB_IDS.items():
        target = root / relative
        if not target.is_file():
            raise InstallationError(relative + ': 기존 프로젝트 파일을 찾을 수 없습니다.')
        old = target.read_bytes()
        source, bom, crlf = _decode(old, relative)
        if MARK not in source and _git_blob_sha(old) != sha:
            raise InstallationError(
                relative + ': Git 기준 커밋 ' + TARGET_COMMIT +
                '과 파일 내용이 다릅니다. 자동 수정하지 않았습니다.\n'
                '  현재 SHA: ' + _git_blob_sha(old) + '\n  예상 SHA: ' + sha
            )
        result = patch_registry(source) if relative.endswith('style_tag_transform_map_service.py') else patch_dispatcher(source)
        if result != source:
            changes.append(Change(target, _encode(result, has_bom=bom, has_crlf=crlf), old))
    for relative, name in ADDED_FILES.items():
        target = root / relative
        bundled = PAYLOAD_DIR / name
        if not bundled.is_file():
            raise InstallationError('압축 내용이 누락됐습니다: ' + name)
        data = bundled.read_bytes()
        source, _, _ = _decode(data, name)
        ast.parse(source)
        if target.exists():
            if not target.is_file() or target.read_bytes() != data:
                raise InstallationError(relative + ': 같은 이름의 다른 파일이 있어 덮어쓰지 않습니다.')
        else:
            changes.append(Change(target, data, None))
    return changes


def _atomic_write(destination: Path, data: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, dir=destination.parent,
                                     prefix='.capstone_install_', suffix='.tmp') as output:
        tmp = Path(output.name)
        output.write(data)
    try:
        os.replace(tmp, destination)
    finally:
        if tmp.exists():
            tmp.unlink()


def install(root: Path) -> list[str]:
    root = Path(root).resolve()
    changes = plan(root)
    if not changes:
        return ['이미 설치돼 있습니다. 변경할 파일이 없습니다.']
    git_dir = root / '.git'
    if not git_dir.is_dir():
        raise InstallationError('.git 디렉터리를 확인하지 못해 안전 백업을 만들 수 없습니다.')
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup_dir = git_dir / 'capstone_install_backups' / ('unmapped_batch1_' + stamp)
    backup_dir.mkdir(parents=True, exist_ok=False)
    for change in changes:
        if change.old_bytes is not None:
            copied = backup_dir / change.path.relative_to(root)
            copied.parent.mkdir(parents=True, exist_ok=True)
            copied.write_bytes(change.old_bytes)
    done: list[Change] = []
    try:
        for change in changes:
            _atomic_write(change.path, change.new_bytes)
            done.append(change)
    except Exception:
        for change in reversed(done):
            try:
                if change.old_bytes is None:
                    change.path.unlink(missing_ok=True)
                else:
                    _atomic_write(change.path, change.old_bytes)
            except Exception:
                pass
        raise InstallationError('설치 중 파일 쓰기 오류로 기존 내용을 복원했습니다.')
    return [f'설치 완료: {len(changes)}개 파일 반영',
            '백업 위치: ' + str(backup_dir),
            '프론트엔드와 스타일 저장 구조는 수정하지 않았습니다.']


def main() -> int:
    parser = argparse.ArgumentParser(description='기존 비교 전용 개념 태그 자동 변환 1차 설치')
    parser.add_argument('--check', action='store_true', help='실제 파일은 변경하지 않고 설치 가능 여부만 확인')
    parser.add_argument('--root', type=Path, default=Path.cwd(), help='Git 프로젝트 최상위 경로')
    options = parser.parse_args()
    try:
        if options.check:
            changes = plan(options.root)
            if changes:
                print('검사 통과: 설치 가능 (' + str(len(changes)) + '개 파일 변경 예정)')
                for change in changes:
                    print(' - ' + str(change.path.relative_to(options.root.resolve())))
            else:
                print('검사 통과: 이미 설치된 상태입니다.')
        else:
            for line in install(options.root):
                print(line)
    except (InstallationError, OSError, SyntaxError) as exc:
        print('설치 중단: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
