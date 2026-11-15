"""Fail-closed Windows/macOS/Linux 9th batch source patch installer.

Checks exact 5th batch cumulative upstream version. Changes only the registry,
dispatcher, plan and four NEW backend files; never edits frontend or saved
style storage. Run in capstone_main: python backend/tools/install_unmapped_batch9.py --check
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

BASE_SHA5 = '7be85c0f0a67d948689ec1e61cea488f46e73a93241e096a1d708eae81ba0b0b'
BATCH8_AUDIT_SHA = 'b27b79c6bbb715feb85cf6b7ef17e0543687e322750b291f983920ac543e9a1a'
BATCH8_TEST_SHA = '246690dac75a84b7e33e7edeb5dfac50f6b506594a8a6072b94c81f75c5b0f18'

REGISTRY = 'backend/app/services/style_tag_transform_map_service.py'
DISPATCH = 'backend/app/services/style_apply_service.py'
PLAN = 'backend/app/services/style_transform_plan_service.py'
UPSTREAM = (REGISTRY, DISPATCH, PLAN)

REGISTRY_ANCHOR = 'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
REGISTRY_INSERT = '''    # CAPSTONE_UNMAPPED_BATCH9_V1: inferred from existing saved metrics, no style-schema changes.
    "range 사용": "create_safe_literal_range",
    "논리 연산": "create_safe_nested_boolean",
    "멤버십 연산": "create_safe_known_membership",
    "sorted 사용": "create_sort_style",
'''
DISPATCH_ANCHOR = 'def _get_transform_function(action: str):\n'
DISPATCH_IMPORT = '''# CAPSTONE_UNMAPPED_BATCH9_V1: conservative source-to-source transformations.
from app.services.improvement.safe_unmapped_patterns_batch9_service import (
    transform_to_literal_range_style,
    transform_to_nested_boolean_style,
    transform_to_known_membership_style,
)

'''
DISPATCH_MAP_ANCHOR = '    action_map = {\n'
DISPATCH_MAP_INSERT = '''        # CAPSTONE_UNMAPPED_BATCH9_V1
        "create_safe_literal_range": transform_to_literal_range_style,
        "create_safe_nested_boolean": transform_to_nested_boolean_style,
        "create_safe_known_membership": transform_to_known_membership_style,
'''
PLAN_ANCHOR = '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n'
PLAN_INSERT = '''    # CAPSTONE_UNMAPPED_BATCH9_V1: infer syntax preferences exclusively from
    # already-persisted metric counters; DO NOT expand the 19 stored syntax tags.
    saved_metrics_b9 = _get_style_metrics(diff)
    target_metrics_b9 = _get_target_metrics(diff)
    for tag_b9, metric_b9, action_b9 in (
        ("range 사용", "range_call_count", "create_safe_literal_range"),
        ("논리 연산", "bool_op_count", "create_safe_nested_boolean"),
        ("멤버십 연산", "membership_op_count", "create_safe_known_membership"),
    ):
        if (_metric_count(saved_metrics_b9, metric_b9) > 0
                and _metric_count(target_metrics_b9, metric_b9) == 0):
            actions.append({
                "tag": tag_b9,
                "action": action_b9,
                "reason": "저장된 스타일의 기존 메트릭 선호를 확인하여 제한된 안전 패턴만 변환합니다.",
            })
    if (_metric_count(saved_metrics_b9, "sorted_call_count") > 0
            and _metric_count(saved_metrics_b9, "sort_method_call_count") == 0
            and _metric_count(target_metrics_b9, "sorted_call_count") == 0
            and _metric_count(target_metrics_b9, "sort_method_call_count") > 0
            and not any(item.get("action") == "create_sort_style" for item in actions)):
        actions.append({
            "tag": "sorted 사용",
            "action": "create_sort_style",
            "reason": "저장된 스타일의 sorted() 호출 선호와 대상 코드의 list.sort()를 비교하여 변환합니다.",
        })

'''

PAYLOAD_DIR = Path(__file__).resolve().parent / 'unmapped_batch9_payload'
NEW = {
    'backend/app/services/improvement/safe_unmapped_patterns_batch9_service.py':
        'safe_unmapped_patterns_batch9_service.py.source',
    'backend/tests/test_style_unmapped_patterns_batch9.py':
        'test_style_unmapped_patterns_batch9.py.source',
    'backend/tests/test_style_unmapped_patterns_batch9_integration.py':
        'test_style_unmapped_patterns_batch9_integration.py.source',
    'backend/tools/audit_transform_three_patterns_batch9.py':
        'audit_transform_three_patterns_batch9.py.source',
}
PAYLOAD_SHA256 = {'safe_unmapped_patterns_batch9_service.py.source': '319f80a2cbe92b2380715783b799f9733b2e6a7341e7a89b9d27824ef3f6e537', 'test_style_unmapped_patterns_batch9.py.source': 'd7fb255bc099eaab11da2301de2f872f19f05e086ea4418999ea6278fc423d99', 'test_style_unmapped_patterns_batch9_integration.py.source': '0f5f8d8b80e5f2e0a6615fdef168d5b22015f73e7c126d163eafa2736a8d4a4f', 'audit_transform_three_patterns_batch9.py.source': 'd694ac5cb268e4e14f27a01d07c139f91c54b2d0993cb55ff9c5861b649c7e9e'}


class InstallationError(Exception):
    pass


@dataclass(frozen=True)
class Change:
    path: Path
    before: bytes | None
    after: bytes


def _decode(data: bytes) -> tuple[str, bool, bool]:
    bom = data.startswith(b'\xef\xbb\xbf')
    source = data[3:] if bom else data
    return source.decode('utf-8').replace('\r\n', '\n'), bom, b'\r\n' in source


def _encode(source: str, bom: bool, crlf: bool) -> bytes:
    if crlf:
        source = source.replace('\n', '\r\n')
    return (b'\xef\xbb\xbf' if bom else b'') + source.encode('utf-8')


def _sha_lf(data: bytes) -> str:
    return sha256(data.removeprefix(b'\xef\xbb\xbf').replace(b'\r\n', b'\n')).hexdigest()


def _once(source: str, anchor: str, inserted: str, label: str) -> str:
    if source.count(anchor) != 1:
        raise InstallationError(f'{label}: 정확히 한 개의 변환 위치가 필요합니다.')
    return source.replace(anchor, inserted + anchor, 1)


def patch_registry(source: str) -> str:
    if 'CAPSTONE_UNMAPPED_BATCH9_V1' in source:
        raise InstallationError('9차 태그 연결이 이미 부분 적용됐습니다.')
    if source.count(REGISTRY_ANCHOR) != 1:
        raise InstallationError(REGISTRY + ': 태그 등록 위치를 찾을 수 없습니다.')
    return source.replace(REGISTRY_ANCHOR, REGISTRY_ANCHOR + REGISTRY_INSERT, 1)


def patch_dispatch(source: str) -> str:
    if 'CAPSTONE_UNMAPPED_BATCH9_V1' in source:
        raise InstallationError('9차 변환기가 이미 부분 적용됐습니다.')
    source = _once(source, DISPATCH_ANCHOR, DISPATCH_IMPORT, DISPATCH)
    if source.count(DISPATCH_MAP_ANCHOR) != 1:
        raise InstallationError(DISPATCH + ': 액션 맵 등록 위치를 찾을 수 없습니다.')
    source = source.replace(DISPATCH_MAP_ANCHOR,
                            DISPATCH_MAP_ANCHOR + DISPATCH_MAP_INSERT, 1)
    return source


def patch_plan(source: str) -> str:
    if 'CAPSTONE_UNMAPPED_BATCH9_V1' in source:
        raise InstallationError('9차 계획이 이미 부분 적용됐습니다.')
    return _once(source, PLAN_ANCHOR, PLAN_INSERT, PLAN)


PATCHERS = {REGISTRY: patch_registry, DISPATCH: patch_dispatch, PLAN: patch_plan}


def _expected_before(root: Path) -> dict[str, str]:
    installer = root / 'backend/tools/install_unmapped_batch5.py'
    if not installer.is_file() or sha256(installer.read_bytes()).hexdigest() != BASE_SHA5:
        raise InstallationError('5차 누적 설치기 기준 버전을 확인하지 못했습니다.')
    b5 = runpy.run_path(str(installer))
    b1, b2, b3, b4 = b5['_prior_patchers'](root)
    originals = {}
    for rel in UPSTREAM:
        value = b5['_expected_prior'](root, rel, b1, b2, b3, b4)
        originals[rel] = {REGISTRY: b5['patch_registry'],
                          DISPATCH: b5['patch_dispatcher'],
                          PLAN: b5['patch_plan']}[rel](value)
    return originals


def preflight(root: Path) -> list[Change]:
    root = root.resolve()
    if not (root / '.git').is_dir() or not (root / 'docker-compose.yml').is_file():
        raise InstallationError('capstone_main Git 저장소의 최상위에서 실행해 주세요.')
    # Fail closed on missing/changed 8th batch evidence assets.
    required = {
        'backend/tools/audit_transform_three_patterns_batch8.py': BATCH8_AUDIT_SHA,
        'backend/tests/test_style_three_pattern_expansion_batch8.py': BATCH8_TEST_SHA,
    }
    for rel, digest in required.items():
        path = root / rel
        if not path.is_file() or _sha_lf(path.read_bytes()) != digest:
            raise InstallationError('8차 패치 파일이 없거나 예상 내용과 다릅니다: ' + rel)
    prior = _expected_before(root)
    changes = []
    for rel in UPSTREAM:
        file = root / rel
        if not file.is_file():
            raise InstallationError('기존 파일을 찾지 못했습니다: ' + rel)
        data = file.read_bytes()
        text, bom, crlf = _decode(data)
        expected = prior[rel]
        updated = PATCHERS[rel](expected)
        ast.parse(updated, filename=rel)
        if text == updated:
            continue
        if text != expected:
            raise InstallationError('기존 코드에 예상 외 수정이 있습니다. 덮어쓰지 않습니다: ' + rel)
        changes.append(Change(file, data, _encode(updated, bom, crlf)))

    for rel, payload_name in NEW.items():
        source, target = PAYLOAD_DIR / payload_name, root / rel
        if not source.is_file():
            raise InstallationError('배포 파일 누락: ' + payload_name)
        data = source.read_bytes()
        if sha256(data).hexdigest() != PAYLOAD_SHA256[payload_name]:
            raise InstallationError('배포 파일 무결성 오류: ' + payload_name)
        ast.parse(data.decode('utf-8'), filename=payload_name)
        if target.exists():
            if not target.is_file() or _sha_lf(target.read_bytes()) != _sha_lf(data):
                raise InstallationError('기존 동명 파일을 덮어쓰지 않습니다: ' + rel)
        else:
            changes.append(Change(target, None, data))
    return changes


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent, prefix='.capstone_b9_',
                                     suffix='.tmp', delete=False) as f:
        temp = Path(f.name)
        f.write(data)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def install(root: Path) -> int:
    root = root.resolve()
    changes = preflight(root)
    if not changes:
        print('9차 패치는 이미 설치돼 있습니다. 변경 사항이 없습니다.')
        return 0
    backups = root / '.git/capstone_batch9_backups' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backups.mkdir(parents=True, exist_ok=False)
    for change in changes:
        if change.before is not None:
            p = backups / change.path.relative_to(root)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(change.before)
    done = []
    try:
        for change in changes:
            _atomic_write(change.path, change.after)
            done.append(change)
    except OSError as exc:
        for change in reversed(done):
            try:
                if change.before is None:
                    change.path.unlink(missing_ok=True)
                else:
                    _atomic_write(change.path, change.before)
            except OSError:
                pass
        raise InstallationError('설치 도중 오류 발생, 수정 파일 복원 시도 완료') from exc
    print(f'9차 설치 완료: {len(changes)}개 파일, 백업: {backups}')
    print('기존 코드 검증 성공; frontend, 스타일 저장 및 주석 제거 파일 변경 없음')
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description='9차 신규 태그 자동 변환 안전 설치기')
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
    except (InstallationError, OSError, SyntaxError, UnicodeError, KeyError, ValueError) as e:
        print('설치 중단: ' + str(e), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
