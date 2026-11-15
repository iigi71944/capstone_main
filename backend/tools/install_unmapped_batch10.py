"""Batch 10 fail-closed incremental installer. Windows/macOS/Linux compatible.

Requires unmodified 9th-batch cumulative source; never changes UI, style
storage, comment cleanup, or existing transformer implementations.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import os
from pathlib import Path
import runpy
import sys
import tempfile

BATCH9_INSTALLER_SHA = 'c073c323d11cd4bbfbbbd23216b280a89735126bede065947b187bcb0f166e29'
BATCH9_AUDIT_SHA = 'd694ac5cb268e4e14f27a01d07c139f91c54b2d0993cb55ff9c5861b649c7e9e'
BATCH9_TEST_SHA = 'd7fb255bc099eaab11da2301de2f872f19f05e086ea4418999ea6278fc423d99'
REGISTRY = 'backend/app/services/style_tag_transform_map_service.py'
DISPATCH = 'backend/app/services/style_apply_service.py'
PLAN = 'backend/app/services/style_transform_plan_service.py'
UPSTREAM = (REGISTRY, DISPATCH, PLAN)

REGISTRY_ANCHOR = 'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
REGISTRY_INSERT = """    # CAPSTONE_UNMAPPED_BATCH10_V1: five newly linked syntax/concept tags.
    "복합 할당": "create_safe_augassign",
    "enumerate 사용": "create_safe_enumerate",
    "키워드 인자 사용": "create_safe_keyword_call",
    "검증 로직 중심 구조": "create_safe_validation_helper",
    "반환 중심 구조": "create_return_structure",
"""
DISPATCH_ANCHOR = 'def _get_transform_function(action: str):\n'
DISPATCH_IMPORT = """# CAPSTONE_UNMAPPED_BATCH10_V1: narrow and source-preserving additions.
from app.services.improvement.safe_unmapped_patterns_batch10_service import (
    transform_to_safe_augassign_style,
    transform_to_safe_enumerate_style,
)

"""
DISPATCH_MAP_ANCHOR = '    action_map = {\n'
DISPATCH_MAP_INSERT = """        # CAPSTONE_UNMAPPED_BATCH10_V1
        "create_safe_augassign": transform_to_safe_augassign_style,
        "create_safe_enumerate": transform_to_safe_enumerate_style,
"""
PLAN_ANCHOR = '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n'
PLAN_INSERT = """    # CAPSTONE_UNMAPPED_BATCH10_V1: use previously saved metric counters;
    # do not add syntax tags beyond the existing 19-tag storage policy.
    saved_metrics_b10 = _get_style_metrics(diff)
    target_metrics_b10 = _get_target_metrics(diff)
    for tag_b10, metric_b10, action_b10 in (
        ("복합 할당", "aug_assign_count", "create_safe_augassign"),
        ("enumerate 사용", "enumerate_call_count", "create_safe_enumerate"),
        ("키워드 인자 사용", "keyword_arg_count", "create_safe_keyword_call"),
    ):
        if (_metric_count(saved_metrics_b10, metric_b10) > 0
                and _metric_count(target_metrics_b10, metric_b10) == 0):
            actions.append({
                "tag": tag_b10,
                "action": action_b10,
                "reason": "기존 저장 메트릭에 근거해 안전한 구문 패턴을 탐색합니다.",
            })

"""

PAYLOAD_DIR = Path(__file__).resolve().parent / 'unmapped_batch10_payload'
NEW = {
    'backend/app/services/improvement/safe_unmapped_patterns_batch10_service.py':
        'safe_unmapped_patterns_batch10_service.py.source',
    'backend/tests/test_style_unmapped_patterns_batch10.py':
        'test_style_unmapped_patterns_batch10.py.source',
    'backend/tests/test_style_unmapped_patterns_batch10_integration.py':
        'test_style_unmapped_patterns_batch10_integration.py.source',
    'backend/tools/audit_transform_three_patterns_batch10.py':
        'audit_transform_three_patterns_batch10.py.source',
}
PAYLOAD_SHA = {'safe_unmapped_patterns_batch10_service.py.source': '1414042052d7e6f56e173eccf7058d8262af2a3ddd58ebc966d77ed7fc1499db', 'test_style_unmapped_patterns_batch10.py.source': '1fecc2d04634d51841ba5ae8844b061b2cc44bce21b8ab8aac5c92fd7aad3e65', 'test_style_unmapped_patterns_batch10_integration.py.source': '2880a2f4df38422d6646a6603d93129e29b7ef177058b7cd76ec257d08cda8c2', 'audit_transform_three_patterns_batch10.py.source': '059688f76506eec955c77195d8e35eddaee9695512f66cbe9a443de4923261bc'}

class InstallationError(Exception):
    pass


@dataclass(frozen=True)
class Change:
    path: Path
    before: bytes | None
    after: bytes


def _decode(data: bytes) -> tuple[str, bool, bool]:
    bom = data.startswith(b'\xef\xbb\xbf')
    body = data[3:] if bom else data
    return body.decode('utf-8').replace('\r\n','\n'), bom, b'\r\n' in body


def _encode(source: str, bom: bool, crlf: bool) -> bytes:
    if crlf:
        source = source.replace('\n','\r\n')
    return (b'\xef\xbb\xbf' if bom else b'') + source.encode('utf-8')


def _sha_lf(data: bytes) -> str:
    return sha256(data.removeprefix(b'\xef\xbb\xbf').replace(b'\r\n',b'\n')).hexdigest()


def _insert_once(source: str, anchor: str, insertion: str, label: str) -> str:
    if source.count(anchor) != 1:
        raise InstallationError(label + ': 기준 코드 위치가 달라 설치 중단')
    return source.replace(anchor, insertion + anchor, 1)


def patch_registry(source: str) -> str:
    if 'CAPSTONE_UNMAPPED_BATCH10_V1' in source:
        raise InstallationError('10차 부분 패치 발견')
    if source.count(REGISTRY_ANCHOR) != 1:
        raise InstallationError('10차 태그 등록 위치를 찾을 수 없음')
    return source.replace(REGISTRY_ANCHOR, REGISTRY_ANCHOR + REGISTRY_INSERT, 1)


def patch_dispatch(source: str) -> str:
    if 'CAPSTONE_UNMAPPED_BATCH10_V1' in source:
        raise InstallationError('10차 변환기 부분 패치 발견')
    source = _insert_once(source, DISPATCH_ANCHOR, DISPATCH_IMPORT, DISPATCH)
    if source.count(DISPATCH_MAP_ANCHOR) != 1:
        raise InstallationError('10차 액션 매핑 위치를 찾을 수 없음')
    return source.replace(DISPATCH_MAP_ANCHOR, DISPATCH_MAP_ANCHOR + DISPATCH_MAP_INSERT, 1)


def patch_plan(source: str) -> str:
    if 'CAPSTONE_UNMAPPED_BATCH10_V1' in source:
        raise InstallationError('10차 계획 부분 패치 발견')
    return _insert_once(source, PLAN_ANCHOR, PLAN_INSERT, PLAN)


PATCHERS = {REGISTRY: patch_registry, DISPATCH: patch_dispatch, PLAN: patch_plan}


def _expected_ninth(root: Path) -> dict[str, str]:
    installer = root / 'backend/tools/install_unmapped_batch9.py'
    if not installer.is_file() or sha256(installer.read_bytes()).hexdigest() != BATCH9_INSTALLER_SHA:
        raise InstallationError('9차 기준 설치기가 누락됐거나 내용이 달라 중단합니다.')
    ninth = runpy.run_path(str(installer))
    originals = ninth['_expected_before'](root)
    return {key: ninth['PATCHERS'][key](originals[key]) for key in UPSTREAM}


def preflight(root: Path) -> list[Change]:
    root = root.resolve()
    if not (root/'.git').is_dir() or not (root/'docker-compose.yml').is_file():
        raise InstallationError('capstone_main 프로젝트 최상위에서 실행해 주세요.')
    for rel, expected in (
        ('backend/tools/audit_transform_three_patterns_batch9.py', BATCH9_AUDIT_SHA),
        ('backend/tests/test_style_unmapped_patterns_batch9.py', BATCH9_TEST_SHA),
    ):
        file = root/rel
        if not file.is_file() or _sha_lf(file.read_bytes()) != expected:
            raise InstallationError('9차 검증 파일 누락/변경: ' + rel)
    prior = _expected_ninth(root)
    changes: list[Change] = []
    for rel in UPSTREAM:
        path = root/rel
        if not path.is_file():
            raise InstallationError('기존 파일 누락: ' + rel)
        old = path.read_bytes()
        source, bom, crlf = _decode(old)
        expected = prior[rel]
        revised = PATCHERS[rel](expected)
        ast.parse(revised, filename=rel)
        if source == revised:
            continue
        if source != expected:
            raise InstallationError('기존 사용자 변경 감지. 덮어쓰지 않음: ' + rel)
        changes.append(Change(path, old, _encode(revised, bom, crlf)))
    for rel, filename in NEW.items():
        source = PAYLOAD_DIR/filename
        target = root/rel
        if not source.is_file():
            raise InstallationError('배포 파일 누락: ' + filename)
        data = source.read_bytes()
        if sha256(data).hexdigest() != PAYLOAD_SHA[filename]:
            raise InstallationError('배포 파일 해시 오류: ' + filename)
        ast.parse(data.decode('utf-8'), filename=filename)
        if target.exists():
            if not target.is_file() or _sha_lf(target.read_bytes()) != _sha_lf(data):
                raise InstallationError('기존 동명 파일을 덮어쓰지 않습니다: ' + rel)
        else:
            changes.append(Change(target, None, data))
    return changes


def _atomic_write(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent, prefix='.capstone10_',
                                     suffix='.tmp', delete=False) as temporary:
        pending = Path(temporary.name)
        temporary.write(contents)
    try:
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def install(root: Path) -> int:
    root = root.resolve()
    changes = preflight(root)
    if not changes:
        print('10차 패치는 이미 설치되어 있습니다. 변경 없음.')
        return 0
    backups = root/'.git/capstone_batch10_backups'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backups.mkdir(parents=True, exist_ok=False)
    for change in changes:
        if change.before is not None:
            backup = backups/change.path.relative_to(root)
            backup.parent.mkdir(parents=True,exist_ok=True)
            backup.write_bytes(change.before)
    done: list[Change] = []
    try:
        for change in changes:
            # Prevent overwriting files changed after preflight.
            if change.before is None and change.path.exists():
                raise InstallationError('검사 후 신규 파일 경로가 생겼습니다: '+str(change.path))
            if change.before is not None and change.path.read_bytes() != change.before:
                raise InstallationError('검사 후 기존 파일 내용이 바뀌었습니다: '+str(change.path))
            _atomic_write(change.path, change.after)
            done.append(change)
    except (OSError, InstallationError) as exc:
        for change in reversed(done):
            try:
                if change.before is None:
                    change.path.unlink(missing_ok=True)
                else:
                    _atomic_write(change.path, change.before)
            except OSError:
                pass
        raise InstallationError('설치 실패, 변경 파일 복원 시도 완료: ' + str(exc)) from exc
    print(f'10차 설치 완료: {len(changes)}개 파일 수정/추가. 백업: {backups}')
    print('기존 프론트엔드, 저장 방식, 주석 제거, 1-9차 코드 유지')
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description='10차 연결 태그 확장 안전 설치')
    p.add_argument('--check', action='store_true')
    p.add_argument('--root', type=Path, default=Path.cwd())
    args = p.parse_args()
    try:
        if args.check:
            changes = preflight(args.root)
            print('사전 검사 통과: 변경 예정 파일', len(changes))
            for change in changes:
                print(' -', change.path.relative_to(args.root.resolve()))
            return 0
        return install(args.root)
    except (InstallationError, OSError, SyntaxError, UnicodeError, KeyError, ValueError) as exc:
        print('설치 중단: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
