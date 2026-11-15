"""Strict, additive installer for previously unmapped concept tags batch 2.

Requires the first batch installed over Git base 832f1b4, and compares the
actual three affected files to reconstructed exact expected source versions.
Never silently overwrites unknown edits. Creates a rollback backup in .git.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from datetime import datetime
import hashlib
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

BASE = '832f1b4'
MARK = 'CAPSTONE_UNMAPPED_BATCH2_V1'
BATCH1_TOOL_SHA256 = '294d6171538fe04f4599b43bcae7eb44aecb22b82d4eec04510800335e3fc6c6'
ROOT_REL = 'backend/tools/unmapped_batch2_payload'
REGISTRY = 'backend/app/services/style_tag_transform_map_service.py'
DISPATCHER = 'backend/app/services/style_apply_service.py'
PLAN = 'backend/app/services/style_transform_plan_service.py'
BASE_GIT_BLOBS = {
    REGISTRY: '0116bf09c48ca76caeba456413386c54a6a8eca6',
    DISPATCHER: '796ce3f37f750be6b2b9517e8e376c101b1308f7',
    PLAN: 'abb6a6795f7bfb0736cea0299b8a008b7de274f5',
}
ADDITIONS = {
    'backend/app/services/improvement/safe_unmapped_patterns_batch2_service.py':
        'safe_unmapped_patterns_batch2_service.py.source',
    'backend/tests/test_style_unmapped_patterns_batch2.py':
        'test_style_unmapped_patterns_batch2.py.source',
}

REGISTRY_ANCHOR = 'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
REGISTRY_INSERT = '''    # CAPSTONE_UNMAPPED_BATCH2_V1: additional concepts, existing stored styles unchanged.
    "데이터 변환 구조": "create_safe_data_comprehension",
    "내장 함수 활용 구조": "create_safe_builtin_sum",
    "검증 로직 중심 구조": "create_safe_validation_condition",
'''
DISPATCH_ANCHOR = 'def _get_transform_function(action: str):\n'
DISPATCH_IMPORT = '''# CAPSTONE_UNMAPPED_BATCH2_V1: source-preserving transforms for stored concept tags.
from app.services.improvement.safe_unmapped_patterns_batch2_service import (
    transform_to_data_comprehension,
    transform_to_builtin_sum,
    transform_to_validation_condition,
)

'''
ACTION_ANCHOR = '    action_map = {\n'
ACTION_INSERT = '''        # CAPSTONE_UNMAPPED_BATCH2_V1: independently checked concept transforms.
        "create_safe_data_comprehension": transform_to_data_comprehension,
        "create_safe_builtin_sum": transform_to_builtin_sum,
        "create_safe_validation_condition": transform_to_validation_condition,
'''
PLAN_ANCHOR = '        actions.append({\n            "tag": tag_name,\n'
PLAN_INSERT = '''        # CAPSTONE_UNMAPPED_BATCH2_V1: do not undo stronger saved preferences.
        # A nested style should not be flattened merely to create a broad
        # validation concept, and a state-mutation style should not be summed.
        saved_concepts = _get_tag_names(diff, "style_concept_names")
        if tag_name == "검증 로직 중심 구조" and saved_concepts & {
            "조건문 중첩 구조", "깊은 중첩 구조"
        }:
            continue
        if tag_name == "내장 함수 활용 구조" and "상태 변경 중심 구조" in saved_concepts:
            continue

'''


class InstallationError(Exception):
    pass


@dataclass(frozen=True)
class Change:
    path: Path
    old_bytes: bytes | None
    new_bytes: bytes


def _blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def _decode(data: bytes, label: str) -> tuple[str, bool, bool]:
    bom = data.startswith(b'\xef\xbb\xbf')
    text = data[3:] if bom else data
    try:
        s = text.decode('utf-8')
    except UnicodeDecodeError as e:
        raise InstallationError(label + ': UTF-8 인코딩 확인 실패') from e
    return s.replace('\r\n', '\n'), bom, b'\r\n' in text


def _encode(s: str, bom: bool, crlf: bool) -> bytes:
    return (b'\xef\xbb\xbf' if bom else b'') + (s.replace('\n', '\r\n') if crlf else s).encode('utf-8')


def _replace_exact(source: str, anchor: str, payload: str, label: str) -> str:
    if source.count(anchor) != 1:
        raise InstallationError(label + ': 기대한 코드 위치를 정확히 한 개 찾지 못했습니다.')
    return source.replace(anchor, payload + anchor, 1)


def _patch_registry(s: str) -> str:
    if MARK in s:
        raise InstallationError('태그 매핑 파일이 부분적으로 이미 수정돼 있습니다.')
    if s.count(REGISTRY_ANCHOR) != 1:
        raise InstallationError('태그 매핑: 등록 위치가 일치하지 않습니다.')
    result = s.replace(REGISTRY_ANCHOR, REGISTRY_ANCHOR + REGISTRY_INSERT, 1)
    ast.parse(result)
    return result


def _patch_dispatch(s: str) -> str:
    if MARK in s:
        raise InstallationError('변환 서비스가 부분적으로 이미 수정돼 있습니다.')
    s = _replace_exact(s, DISPATCH_ANCHOR, DISPATCH_IMPORT, '변환 서비스 import')
    if s.count(ACTION_ANCHOR) != 1:
        raise InstallationError('변환 서비스 액션: 등록 위치가 일치하지 않습니다.')
    s = s.replace(ACTION_ANCHOR, ACTION_ANCHOR + ACTION_INSERT, 1)
    ast.parse(s)
    return s


def _patch_plan(s: str) -> str:
    if MARK in s:
        raise InstallationError('변환 계획이 부분적으로 이미 수정돼 있습니다.')
    s = _replace_exact(s, PLAN_ANCHOR, PLAN_INSERT, '변환 충돌 방지')
    ast.parse(s)
    return s


def _git_show(root: Path, path: str) -> str:
    cmd = ['git', '-C', str(root), 'show', BASE + ':' + path]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise InstallationError('Git 기준 소스를 조회하지 못했습니다.') from e
    if proc.returncode != 0:
        raise InstallationError('기준 Git 커밋 ' + BASE + '을 찾지 못했습니다: ' + path)
    if _blob(proc.stdout) != BASE_GIT_BLOBS[path]:
        raise InstallationError('Git 기준 파일 해시가 일치하지 않습니다: ' + path)
    return _decode(proc.stdout, path)[0]


def _expected_before(root: Path, path: str, batch1: dict) -> str:
    source = _git_show(root, path)
    if path == REGISTRY:
        return batch1['patch_registry'](source)
    if path == DISPATCHER:
        return batch1['patch_dispatcher'](source)
    return source


def plan(root: Path) -> list[Change]:
    root = root.resolve()
    if not (root / '.git').is_dir() or not (root / 'docker-compose.yml').is_file():
        raise InstallationError('capstone_main Git 프로젝트의 최상위 폴더에서 실행해 주세요.')
    previous = root / 'backend/tools/install_unmapped_batch1.py'
    if not previous.is_file() or hashlib.sha256(previous.read_bytes()).hexdigest() != BATCH1_TOOL_SHA256:
        raise InstallationError('1차 설치 도구를 확인하지 못했습니다. 이전 패치 설치 상태를 점검해 주세요.')
    batch1 = runpy.run_path(str(previous))
    changes: list[Change] = []
    patchers = {REGISTRY: _patch_registry, DISPATCHER: _patch_dispatch, PLAN: _patch_plan}
    for rel, patcher in patchers.items():
        dest = root / rel
        if not dest.is_file():
            raise InstallationError('기존 프로젝트 파일이 없습니다: ' + rel)
        raw = dest.read_bytes()
        actual, bom, crlf = _decode(raw, rel)
        expected_before = _expected_before(root, rel, batch1)
        expected_after = patcher(expected_before)
        if actual == expected_after:
            continue
        if actual != expected_before:
            raise InstallationError(
                rel + ': 직전 패치 기준 파일과 다릅니다. 기존 코드를 보호하기 위해 중단했습니다.\n'
                'Git diff 또는 변경 파일을 확인한 뒤 맞춤 패치가 필요합니다.'
            )
        changes.append(Change(dest, raw, _encode(expected_after, bom, crlf)))
    for rel, file_name in ADDITIONS.items():
        dest = root / rel
        bundle = Path(__file__).resolve().parent / 'unmapped_batch2_payload' / file_name
        if not bundle.is_file():
            raise InstallationError('배포 파일이 누락됐습니다: ' + file_name)
        data = bundle.read_bytes()
        ast.parse(_decode(data, file_name)[0])
        if dest.exists():
            if not dest.is_file() or dest.read_bytes() != data:
                raise InstallationError(rel + ': 기존 동명 파일이 달라서 덮어쓰지 않습니다.')
        else:
            changes.append(Change(dest, None, data))
    return changes


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='wb', dir=str(path.parent), delete=False,
                                     prefix='.capstone_b2_', suffix='.tmp') as handle:
        tmp = Path(handle.name)
        handle.write(data)
    try:
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def install(root: Path) -> list[str]:
    root = root.resolve()
    changes = plan(root)
    if not changes:
        return ['이미 설치돼 있습니다. 변경 사항이 없습니다.']
    backup = (root / '.git' / 'capstone_install_backups' /
              ('unmapped_batch2_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
    backup.mkdir(parents=True, exist_ok=False)
    for ch in changes:
        if ch.old_bytes is not None:
            target = backup / ch.path.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(ch.old_bytes)
    applied: list[Change] = []
    try:
        for ch in changes:
            _write(ch.path, ch.new_bytes)
            applied.append(ch)
    except Exception as e:
        for ch in reversed(applied):
            try:
                if ch.old_bytes is None:
                    ch.path.unlink(missing_ok=True)
                else:
                    _write(ch.path, ch.old_bytes)
            except OSError:
                pass
        raise InstallationError('설치 중 오류가 발생해 변경된 파일을 복원했습니다.') from e
    return [f'설치 완료: {len(changes)}개 파일', '백업: ' + str(backup),
            '프론트엔드·스타일 저장 형식 변경 없음']


def main() -> int:
    parser = argparse.ArgumentParser(description='캡스톤 비교용 개념 태그 자동 변환 2차 패치')
    parser.add_argument('--check', action='store_true', help='설치 전 검증만 수행')
    parser.add_argument('--root', type=Path, default=Path.cwd(), help='capstone_main 최상위 경로')
    args = parser.parse_args()
    try:
        if args.check:
            changes = plan(args.root)
            print('검사 통과: ' + (f'{len(changes)}개 파일 수정 예정' if changes else '이미 설치됨'))
            for change in changes:
                print(' - ' + str(change.path.relative_to(args.root.resolve())))
        else:
            for line in install(args.root):
                print(line)
    except (InstallationError, OSError, ValueError, SyntaxError) as e:
        print('설치 중단: ' + str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
