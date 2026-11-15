"""Strict cumulative installer for capstone auto-transform batch 3.

Requires both unmapped batches 1 and 2 on the Git 832f1b4 base. Reconstructs
exact expected current source before touching production files. On mismatch,
it exits without overwriting anything. Backup and rollback are in .git.
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
MARK = 'CAPSTONE_UNMAPPED_BATCH3_V1'
PREVIOUS_TOOLS = {
    'install_unmapped_batch1.py': '294d6171538fe04f4599b43bcae7eb44aecb22b82d4eec04510800335e3fc6c6',
    'install_unmapped_batch2.py': '6476ac50b3fa3ba9fe61cb7a10017baa9dcd8afc620a4687226224d1cca31dd3',
}
REGISTRY = 'backend/app/services/style_tag_transform_map_service.py'
DISPATCHER = 'backend/app/services/style_apply_service.py'
PLAN = 'backend/app/services/style_transform_plan_service.py'
ORIGINAL_BLOBS = {
    REGISTRY: '0116bf09c48ca76caeba456413386c54a6a8eca6',
    DISPATCHER: '796ce3f37f750be6b2b9517e8e376c101b1308f7',
    PLAN: 'abb6a6795f7bfb0736cea0299b8a008b7de274f5',
}
PAYLOAD_DIR = Path(__file__).resolve().parent / 'unmapped_batch3_payload'
NEW_FILES = {
    'backend/app/services/improvement/safe_unmapped_patterns_batch3_service.py':
        'safe_unmapped_patterns_batch3_service.py.source',
    'backend/tests/test_style_unmapped_patterns_batch3.py':
        'test_style_unmapped_patterns_batch3.py.source',
}
PAYLOAD_SHA256 = {
    'safe_unmapped_patterns_batch3_service.py.source': '75243a2dd542aa693635b8a0a809fa9db0ee918ee5e8ddd447900538a07aaf7c',
    'test_style_unmapped_patterns_batch3.py.source': 'f88d3dbebd85e54e275f7dac0c851a33c3230dfc6d1e59ea7c7a1e0c33234913',
}

REGISTRY_ANCHOR = 'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
REGISTRY_INSERT = '''    # CAPSTONE_UNMAPPED_BATCH3_V1: metric-directed syntax preferences; style JSON unchanged.
    "복합 할당": "create_safe_augmented_assignment",
    "딕셔너리 메서드 호출": "create_safe_dict_get",
    "for문": "create_counted_while_to_for",
'''
DISPATCH_ANCHOR = 'def _get_transform_function(action: str):\n'
DISPATCH_IMPORT = '''# CAPSTONE_UNMAPPED_BATCH3_V1: conservative, byte-splice source edits.
from app.services.improvement.safe_unmapped_patterns_batch3_service import (
    transform_to_augmented_assignment,
    transform_to_dict_get,
)

'''
DISPATCH_MAP_ANCHOR = '    action_map = {\n'
DISPATCH_MAP_INSERT = '''        # CAPSTONE_UNMAPPED_BATCH3_V1: metric-driven syntax preference actions.
        "create_safe_augmented_assignment": transform_to_augmented_assignment,
        "create_safe_dict_get": transform_to_dict_get,
'''
PLAN_ANCHOR = '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n'
PLAN_INSERT = '''    # CAPSTONE_UNMAPPED_BATCH3_V1: style syntax list stays at 19 entries.
    # Two omitted syntax preferences are inferred from the stored metrics.
    # Avoid adding generated syntax merely because a tag exists in the registry.
    saved_metrics = _get_style_metrics(diff)
    current_metrics = _get_target_metrics(diff)
    if (_metric_count(saved_metrics, "aug_assign_count") > 0
            and _metric_count(current_metrics, "aug_assign_count") == 0):
        actions.append({
            "tag": "복합 할당",
            "action": "create_safe_augmented_assignment",
            "reason": "저장 스타일의 복합 할당 선호도가 관측되어 정수 리터럴 누적 대입에 한정해 적용합니다.",
        })
    if (_metric_count(saved_metrics, "dict_method_call_count") > 0
            and _metric_count(current_metrics, "dict_method_call_count") == 0
            and "딕셔너리 기반 매핑 구조" in _get_tag_names(diff, "style_concept_names")):
        actions.append({
            "tag": "딕셔너리 메서드 호출",
            "action": "create_safe_dict_get",
            "reason": "저장 스타일의 딕셔너리 메서드 선호도가 관측되어 확정된 키 조회에만 적용합니다.",
        })

'''


class InstallationError(Exception):
    pass


@dataclass(frozen=True)
class Change:
    path: Path
    before: bytes | None
    after: bytes


def _blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def _decode(data: bytes, path: str) -> tuple[str, bool, bool]:
    bom = data.startswith(b'\xef\xbb\xbf')
    value = data[3:] if bom else data
    try:
        source = value.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise InstallationError(path + ': UTF-8 인코딩이 아닙니다.') from exc
    return source.replace('\r\n', '\n'), bom, b'\r\n' in value


def _encode(source: str, bom: bool, crlf: bool) -> bytes:
    result = source.replace('\n', '\r\n') if crlf else source
    return (b'\xef\xbb\xbf' if bom else b'') + result.encode('utf-8')


def _replace_once(source: str, anchor: str, replacement: str, path: str) -> str:
    if source.count(anchor) != 1:
        raise InstallationError(path + ': 수정 위치가 예상과 다르므로 중단합니다.')
    return source.replace(anchor, replacement, 1)


def patch_registry(source: str) -> str:
    if MARK in source:
        raise InstallationError('3차 태그 매핑이 이미 부분적으로 설치돼 있습니다.')
    output = _replace_once(source, REGISTRY_ANCHOR, REGISTRY_ANCHOR + REGISTRY_INSERT, REGISTRY)
    ast.parse(output)
    return output


def patch_dispatch(source: str) -> str:
    if MARK in source:
        raise InstallationError('3차 변환 서비스가 이미 부분적으로 설치돼 있습니다.')
    output = _replace_once(source, DISPATCH_ANCHOR, DISPATCH_IMPORT + DISPATCH_ANCHOR, DISPATCHER)
    output = _replace_once(output, DISPATCH_MAP_ANCHOR,
                           DISPATCH_MAP_ANCHOR + DISPATCH_MAP_INSERT, DISPATCHER)
    ast.parse(output)
    return output


def patch_plan(source: str) -> str:
    if MARK in source:
        raise InstallationError('3차 변환 계획이 이미 부분적으로 설치돼 있습니다.')
    output = _replace_once(source, PLAN_ANCHOR, PLAN_INSERT + PLAN_ANCHOR, PLAN)
    ast.parse(output)
    return output


def _git_original(root: Path, relative: str) -> str:
    try:
        proc = subprocess.run(['git', '-C', str(root), 'show', f'{BASE}:{relative}'],
                              capture_output=True, timeout=12, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallationError('기준 Git 커밋 파일을 조회하지 못했습니다.') from exc
    if proc.returncode or _blob(proc.stdout) != ORIGINAL_BLOBS[relative]:
        raise InstallationError(f'{relative}: Git {BASE} 원본을 확인하지 못했습니다.')
    return _decode(proc.stdout, relative)[0]


def _prior_patchers(root: Path) -> tuple[dict, dict]:
    found = []
    for filename, expected_sha in PREVIOUS_TOOLS.items():
        tool_path = root / 'backend/tools' / filename
        if (not tool_path.is_file()
                or hashlib.sha256(tool_path.read_bytes()).hexdigest() != expected_sha):
            raise InstallationError(filename + ': 이전 패치 설치 도구가 예상 버전과 다릅니다.')
        found.append(runpy.run_path(str(tool_path)))
    return found[0], found[1]


def _expected_prior(root: Path, relative: str, b1: dict, b2: dict) -> str:
    source = _git_original(root, relative)
    if relative == REGISTRY:
        source = b1['patch_registry'](source)
        source = b2['_patch_registry'](source)
    elif relative == DISPATCHER:
        source = b1['patch_dispatcher'](source)
        source = b2['_patch_dispatch'](source)
    else:
        source = b2['_patch_plan'](source)
    return source


def plan(root: Path) -> list[Change]:
    root = root.resolve()
    if not (root / '.git').is_dir() or not (root / 'docker-compose.yml').is_file():
        raise InstallationError('capstone_main 프로젝트 최상위 폴더에서 실행해야 합니다.')
    b1, b2 = _prior_patchers(root)
    changes: list[Change] = []
    patchers = {REGISTRY: patch_registry, DISPATCHER: patch_dispatch, PLAN: patch_plan}
    for relative, patcher in patchers.items():
        destination = root / relative
        if not destination.is_file():
            raise InstallationError(relative + ': 기존 파일이 없습니다.')
        old = destination.read_bytes()
        current, bom, crlf = _decode(old, relative)
        expected_before = _expected_prior(root, relative, b1, b2)
        expected_after = patcher(expected_before)
        if current == expected_after:
            continue
        if current != expected_before:
            raise InstallationError(relative + ': 예상과 다른 수정이 감지되어 파일을 보호합니다.')
        changes.append(Change(destination, old, _encode(expected_after, bom, crlf)))
    for relative, filename in NEW_FILES.items():
        destination = root / relative
        source_path = PAYLOAD_DIR / filename
        if not source_path.is_file():
            raise InstallationError('압축 배포 파일이 누락됐습니다: ' + filename)
        payload = source_path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != PAYLOAD_SHA256[filename]:
            raise InstallationError(filename + ': 배포 파일 해시가 일치하지 않습니다.')
        ast.parse(_decode(payload, filename)[0])
        if destination.exists():
            if not destination.is_file() or destination.read_bytes() != payload:
                raise InstallationError(relative + ': 기존 파일과 충돌합니다. 덮어쓰지 않습니다.')
        else:
            changes.append(Change(destination, None, payload))
    return changes


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent, prefix='.capstone_b3_',
                                     suffix='.tmp', delete=False) as output:
        temporary = Path(output.name)
        output.write(data)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def install(root: Path) -> list[str]:
    root = root.resolve()
    changes = plan(root)
    if not changes:
        return ['이미 3차 패치가 설치돼 있습니다. 변경할 파일이 없습니다.']
    folder = (root / '.git' / 'capstone_install_backups' /
              ('unmapped_batch3_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
    folder.mkdir(parents=True, exist_ok=False)
    for change in changes:
        if change.before is not None:
            backup_path = folder / change.path.relative_to(root)
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            backup_path.write_bytes(change.before)
    completed: list[Change] = []
    try:
        for change in changes:
            _atomic_write(change.path, change.after)
            completed.append(change)
    except Exception as exc:
        for change in reversed(completed):
            try:
                if change.before is None:
                    change.path.unlink(missing_ok=True)
                else:
                    _atomic_write(change.path, change.before)
            except OSError:
                pass
        raise InstallationError('설치 오류로 변경 파일을 복원했습니다.') from exc
    return [f'설치 완료: {len(changes)}개 파일', '백업: ' + str(folder),
            '스타일 저장·프론트엔드 변경 없음']


def main() -> int:
    parser = argparse.ArgumentParser(description='캡스톤 자동 변환 태그 확장 3차 안전 설치')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        if args.check:
            changes = plan(args.root)
            print('검사 통과: ' + (f'{len(changes)}개 파일 설치 예정' if changes else '이미 설치 완료'))
            for ch in changes:
                print(' - ' + str(ch.path.relative_to(args.root.resolve())))
        else:
            for line in install(args.root):
                print(line)
    except (InstallationError, OSError, SyntaxError, ValueError, KeyError) as exc:
        print('설치 중단: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
