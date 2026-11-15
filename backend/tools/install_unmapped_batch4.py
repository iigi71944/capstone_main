"""Cumulative, fail-closed capstone batch-4 installer.

Requires original Git commit 832f1b4 and the exact installer scripts for
batches 1, 2, 3. Computes the expected cumulative state from Git, refuses
unexpected changes, and writes a backup in .git before any replacement.

Usage at capstone_main root:
  python backend/tools/install_unmapped_batch4.py --check
  python backend/tools/install_unmapped_batch4.py
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
MARK = 'CAPSTONE_UNMAPPED_BATCH4_V1'
PREVIOUS_TOOLS = {
    'install_unmapped_batch1.py': '294d6171538fe04f4599b43bcae7eb44aecb22b82d4eec04510800335e3fc6c6',
    'install_unmapped_batch2.py': '6476ac50b3fa3ba9fe61cb7a10017baa9dcd8afc620a4687226224d1cca31dd3',
    'install_unmapped_batch3.py': '418607a9b2902f9d8292cbdaae168b51e19fb94e189aadb442da56f250fe8849',
}
REGISTRY = 'backend/app/services/style_tag_transform_map_service.py'
DISPATCHER = 'backend/app/services/style_apply_service.py'
PLAN = 'backend/app/services/style_transform_plan_service.py'
ORIGINAL_BLOBS = {
    REGISTRY: '0116bf09c48ca76caeba456413386c54a6a8eca6',
    DISPATCHER: '796ce3f37f750be6b2b9517e8e376c101b1308f7',
    PLAN: 'abb6a6795f7bfb0736cea0299b8a008b7de274f5',
}
PAYLOAD_DIR = Path(__file__).resolve().parent / 'unmapped_batch4_payload'
NEW_FILES = {
    'backend/app/services/improvement/safe_unmapped_patterns_batch4_service.py':
        'safe_unmapped_patterns_batch4_service.py.source',
    'backend/tests/test_style_unmapped_patterns_batch4.py':
        'test_style_unmapped_patterns_batch4.py.source',
}
PAYLOAD_SHA256 = {
    'safe_unmapped_patterns_batch4_service.py.source': 'ecbfbf63b0329bcb4f2dac994861d77c388083e1620fe57f9d69e1825c00fc01',
    'test_style_unmapped_patterns_batch4.py.source': '3a88d1229dd32f2e6209168a666942958d95857f38663d1e83b1a4788cad77f7',
}

REGISTRY_ANCHOR = 'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
REGISTRY_INSERT = '''    # CAPSTONE_UNMAPPED_BATCH4_V1: syntax preferences inferred from existing style metrics.
    "리스트 리터럴": "create_safe_list_literal",
    "딕셔너리 리터럴": "create_safe_dict_literal",
    "튜플 리터럴": "create_safe_tuple_literal",
'''
DISPATCH_ANCHOR = 'def _get_transform_function(action: str):\n'
DISPATCH_IMPORT = '''# CAPSTONE_UNMAPPED_BATCH4_V1: three restricted source-preserving literal transformations.
from app.services.improvement.safe_unmapped_patterns_batch4_service import (
    transform_to_list_literal,
    transform_to_dict_literal,
    transform_to_tuple_literal,
)

'''
DISPATCH_MAP_ANCHOR = '    action_map = {\n'
DISPATCH_MAP_INSERT = '''        # CAPSTONE_UNMAPPED_BATCH4_V1: syntax-literal constructors.
        "create_safe_list_literal": transform_to_list_literal,
        "create_safe_dict_literal": transform_to_dict_literal,
        "create_safe_tuple_literal": transform_to_tuple_literal,
'''
PLAN_ANCHOR = '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n'
PLAN_INSERT = '''    # CAPSTONE_UNMAPPED_BATCH4_V1: no changes to the 19-item syntax storage filter.
    # Existing metrics provide evidence for literal preferences. Avoid creating
    # missing tags blindly: only supported constant constructors are rewritten.
    saved_metrics_b4 = _get_style_metrics(diff)
    target_metrics_b4 = _get_target_metrics(diff)
    for tag_b4, metric_b4, action_b4 in (
        ("리스트 리터럴", "list_literal_count", "create_safe_list_literal"),
        ("딕셔너리 리터럴", "dict_literal_count", "create_safe_dict_literal"),
        ("튜플 리터럴", "tuple_literal_count", "create_safe_tuple_literal"),
    ):
        if (_metric_count(saved_metrics_b4, metric_b4) > 0
                and _metric_count(target_metrics_b4, metric_b4) == 0):
            actions.append({
                "tag": tag_b4,
                "action": action_b4,
                "reason": "저장 스타일에서 관측한 리터럴 표현을 동등성이 검토된 생성자 패턴에 적용합니다.",
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
        raise InstallationError(path + ': UTF-8 파일이 아닙니다.') from exc
    return source.replace('\r\n', '\n'), bom, b'\r\n' in value


def _encode(source: str, bom: bool, crlf: bool) -> bytes:
    value = source.replace('\n', '\r\n') if crlf else source
    return (b'\xef\xbb\xbf' if bom else b'') + value.encode('utf-8')


def _once(source: str, anchor: str, replacement: str, path: str) -> str:
    if source.count(anchor) != 1:
        raise InstallationError(path + ': 예상했던 코드 위치를 찾지 못했습니다.')
    return source.replace(anchor, replacement, 1)


def patch_registry(source: str) -> str:
    if MARK in source:
        raise InstallationError('4차 태그 매핑이 이미 부분적으로 적용돼 있습니다.')
    output = _once(source, REGISTRY_ANCHOR,
                   REGISTRY_ANCHOR + REGISTRY_INSERT, REGISTRY)
    ast.parse(output)
    return output


def patch_dispatcher(source: str) -> str:
    if MARK in source:
        raise InstallationError('4차 변환 서비스가 이미 부분적으로 적용돼 있습니다.')
    output = _once(source, DISPATCH_ANCHOR, DISPATCH_IMPORT + DISPATCH_ANCHOR, DISPATCHER)
    output = _once(output, DISPATCH_MAP_ANCHOR,
                   DISPATCH_MAP_ANCHOR + DISPATCH_MAP_INSERT, DISPATCHER)
    ast.parse(output)
    return output


def patch_plan(source: str) -> str:
    if MARK in source:
        raise InstallationError('4차 변환 계획이 이미 부분적으로 적용돼 있습니다.')
    output = _once(source, PLAN_ANCHOR, PLAN_INSERT + PLAN_ANCHOR, PLAN)
    ast.parse(output)
    return output


def _git_original(root: Path, relative: str) -> str:
    try:
        proc = subprocess.run(['git', '-C', str(root), 'show', f'{BASE}:{relative}'],
                              capture_output=True, timeout=12, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallationError('기준 Git 커밋을 조회하지 못했습니다.') from exc
    if proc.returncode != 0 or _blob(proc.stdout) != ORIGINAL_BLOBS[relative]:
        raise InstallationError(relative + ': Git 832f1b4 기준 소스를 확인할 수 없습니다.')
    return _decode(proc.stdout, relative)[0]


def _prior_patchers(root: Path) -> tuple[dict, dict, dict]:
    found: list[dict] = []
    for filename, expected_sha in PREVIOUS_TOOLS.items():
        path = root / 'backend/tools' / filename
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
            raise InstallationError(filename + ': 이전 패치 설치 도구가 없거나 예상 버전과 다릅니다.')
        found.append(runpy.run_path(str(path)))
    return found[0], found[1], found[2]


def _expected_prior(root: Path, relative: str, b1: dict, b2: dict, b3: dict) -> str:
    value = _git_original(root, relative)
    if relative == REGISTRY:
        value = b1['patch_registry'](value)
        value = b2['_patch_registry'](value)
        return b3['patch_registry'](value)
    if relative == DISPATCHER:
        value = b1['patch_dispatcher'](value)
        value = b2['_patch_dispatch'](value)
        return b3['patch_dispatch'](value)
    value = b2['_patch_plan'](value)
    return b3['patch_plan'](value)


def plan(root: Path) -> list[Change]:
    root = root.resolve()
    if not (root / '.git').is_dir() or not (root / 'docker-compose.yml').is_file():
        raise InstallationError('capstone_main 저장소의 최상위 폴더에서 실행해 주세요.')
    b1, b2, b3 = _prior_patchers(root)
    changes: list[Change] = []
    patchers = {REGISTRY: patch_registry, DISPATCHER: patch_dispatcher, PLAN: patch_plan}
    for relative, patcher in patchers.items():
        target = root / relative
        if not target.is_file():
            raise InstallationError(relative + ': 기존 파일이 없습니다.')
        old = target.read_bytes()
        current, bom, crlf = _decode(old, relative)
        expected_before = _expected_prior(root, relative, b1, b2, b3)
        expected_after = patcher(expected_before)
        if current == expected_after:
            continue
        if current != expected_before:
            raise InstallationError(relative + ': 예상하지 않은 수정이 발견되어 중단합니다. 파일을 덮어쓰지 않습니다.')
        changes.append(Change(target, old, _encode(expected_after, bom, crlf)))
    for relative, filename in NEW_FILES.items():
        target = root / relative
        payload_path = PAYLOAD_DIR / filename
        if not payload_path.is_file():
            raise InstallationError('배포 파일 누락: ' + filename)
        payload = payload_path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != PAYLOAD_SHA256[filename]:
            raise InstallationError(filename + ': 배포 파일 무결성 검사 실패')
        ast.parse(_decode(payload, filename)[0])
        if target.exists():
            if not target.is_file() or target.read_bytes() != payload:
                raise InstallationError(relative + ': 기존 파일과 충돌하여 중단합니다.')
        else:
            changes.append(Change(target, None, payload))
    return changes


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent, prefix='.capstone_b4_',
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
        return ['4차 패치가 이미 설치돼 있습니다. 추가로 수정한 파일은 없습니다.']
    backup = (root / '.git' / 'capstone_install_backups' /
              ('unmapped_batch4_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
    backup.mkdir(parents=True, exist_ok=False)
    for change in changes:
        if change.before is not None:
            copy = backup / change.path.relative_to(root)
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(change.before)
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
        raise InstallationError('설치 실패: 변경 파일의 복원을 시도했습니다.') from exc
    return [f'설치 완료: {len(changes)}개 파일', '백업 위치: ' + str(backup),
            '기존 스타일 저장·프론트엔드 파일 변경 없음']


def main() -> int:
    parser = argparse.ArgumentParser(description='캡스톤 자동 변환 확장 4차 안전 설치 도구')
    parser.add_argument('--check', action='store_true', help='수정 없이 사전 검사')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        if args.check:
            changes = plan(args.root)
            print('검사 통과: ' + (f'{len(changes)}개 파일 설치 예정' if changes else '이미 설치 완료'))
            for change in changes:
                print(' - ' + str(change.path.relative_to(args.root.resolve())))
        else:
            for line in install(args.root):
                print(line)
    except (InstallationError, OSError, SyntaxError, ValueError, KeyError) as exc:
        print('설치 중단: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
