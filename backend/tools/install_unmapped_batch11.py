"""Batch 11 conservative installer: Windows LF/CRLF and macOS/Linux LF.

Preflight before writes; reject duplicate or unexpected action names; backup;
rollback on errors; write only three existing backend files plus new files.
No frontend, style persistence, or comment-removal source files are touched.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import os
from pathlib import Path
import sys
import tempfile

REGISTRY = 'backend/app/services/style_tag_transform_map_service.py'
DISPATCH = 'backend/app/services/style_apply_service.py'
PLAN = 'backend/app/services/style_transform_plan_service.py'
RULES = 'backend/app/services/tag_rule_service.py'
CORRECTED_AUDIT = 'backend/tools/audit_transform_three_patterns_batch10.py'
CORRECTED_TEST = 'backend/tests/test_style_unmapped_patterns_batch10_integration.py'
CORRECTION_INSTALLER = 'backend/tools/repair_batch10_duplicate_tags.py'

# Exact output of the user-verified Batch 10 duplicate repair.
PRIOR_SHA = {'backend/tools/repair_batch10_duplicate_tags.py': '43b8205543c275313268cf87c979eecaf22cbac4c945b1a6dfef47d78e65c030', 'backend/tests/test_style_unmapped_patterns_batch10_integration.py': '75aaaaf159ee3998b786118d8884ba6c195cb864403cad2836c2cc9afa453f67', 'backend/tools/audit_transform_three_patterns_batch10.py': 'a7ae3b1ebe0e30c20175f8ebbda0f8dedd4a903b8028fc69501d839991ff45e0'}
PAYLOAD_SHA = {'safe_unmapped_patterns_batch11_service.py.source': 'b773295ed23eeb796c846ff457e49247ecb2905cd64b55b126b6bc185272cb9f', 'test_style_unmapped_patterns_batch11.py.source': '84ff0860d5f18cd0fe2d5c373d355a8e22e16ed60fa48c876ff982bc4464b993', 'test_style_unmapped_patterns_batch11_integration.py.source': 'a5d3d97a8ad76c48f3830d08a5f8b2732f3f7249b183d7bfa74d2364fde54e67', 'audit_transform_three_patterns_batch11.py.source': '9d0348e9d09cbd05d128b9e42841c3386648c9327702eb2369002bcfca86a836'}

NEW = {
    'backend/app/services/improvement/safe_unmapped_patterns_batch11_service.py':
        'safe_unmapped_patterns_batch11_service.py.source',
    'backend/tests/test_style_unmapped_patterns_batch11.py':
        'test_style_unmapped_patterns_batch11.py.source',
    'backend/tests/test_style_unmapped_patterns_batch11_integration.py':
        'test_style_unmapped_patterns_batch11_integration.py.source',
    'backend/tools/audit_transform_three_patterns_batch11.py':
        'audit_transform_three_patterns_batch11.py.source',
}
PAYLOAD_DIR = Path(__file__).resolve().parent / 'unmapped_batch11_payload'

REGISTRY_ANCHOR = 'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
REGISTRY_INSERT = '''    # CAPSTONE_UNMAPPED_BATCH11_REGISTRY_V1: three genuinely new tag links.
    "len 사용": "create_safe_literal_len",
    "zip 사용": "create_safe_literal_zip",
    "슬라이싱 사용": "create_safe_list_slice",
'''
DISPATCH_ANCHOR = 'def _get_transform_function(action: str):\n'
DISPATCH_IMPORT = '''# CAPSTONE_UNMAPPED_BATCH11_IMPORT_V1
from app.services.improvement.safe_unmapped_patterns_batch11_service import (
    transform_to_safe_literal_len_style,
    transform_to_safe_literal_zip_style,
    transform_to_safe_list_slice_style,
)

'''
DISPATCH_MAP_ANCHOR = '    action_map = {\n'
DISPATCH_MAP_INSERT = '''        # CAPSTONE_UNMAPPED_BATCH11_MAP_V1
        "create_safe_literal_len": transform_to_safe_literal_len_style,
        "create_safe_literal_zip": transform_to_safe_literal_zip_style,
        "create_safe_list_slice": transform_to_safe_list_slice_style,
'''
PLAN_ANCHOR = '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n'
PLAN_INSERT = '''    # CAPSTONE_UNMAPPED_BATCH11_PLAN_V1: no change to the 19 saved syntax tags.
    # The same stored metric fields already used by previous style records
    # indicate preferences; require evidence in the candidate target as well.
    saved_b11 = _get_style_metrics(diff)
    target_b11 = _get_target_metrics(diff)
    for tag_b11, desired_b11, evidence_b11, action_b11 in (
        ("len 사용", "len_call_count", "sum_call_count", "create_safe_literal_len"),
        ("zip 사용", "zip_call_count", "loop_count", "create_safe_literal_zip"),
        ("슬라이싱 사용", "slicing_count", "list_method_call_count", "create_safe_list_slice"),
    ):
        if (_metric_count(saved_b11, desired_b11) > 0
                and _metric_count(target_b11, desired_b11) == 0
                and _metric_count(target_b11, evidence_b11) > 0):
            actions.append({
                "tag": tag_b11,
                "action": action_b11,
                "reason": "저장된 기존 메트릭으로 확인한 스타일 선호를 제한된 안전 패턴에 적용합니다.",
            })

'''

EXPECTED_EXISTING = {
    '복합 할당': 'create_safe_augmented_assignment',
    '키워드 인자 사용': 'create_safe_keyword_call',
    '검증 로직 중심 구조': 'create_safe_validation_condition',
    '반환 중심 구조': 'create_safe_multiple_returns',
    'enumerate 사용': 'create_safe_enumerate',
    'range 사용': 'create_safe_literal_range',
    '논리 연산': 'create_safe_nested_boolean',
    '멤버십 연산': 'create_safe_known_membership',
    'sorted 사용': 'create_sort_style',
}
EXPECTED_NEW = {
    'len 사용': 'create_safe_literal_len',
    'zip 사용': 'create_safe_literal_zip',
    '슬라이싱 사용': 'create_safe_list_slice',
}


class InstallationError(Exception):
    pass


@dataclass(frozen=True)
class Change:
    path: Path
    old: bytes | None
    new: bytes


def _lf_digest(data: bytes) -> str:
    return sha256(data.removeprefix(b'\xef\xbb\xbf').replace(b'\r\n', b'\n')).hexdigest()


def _decode(data: bytes) -> tuple[str, bool, bool]:
    bom = data.startswith(b'\xef\xbb\xbf')
    source = data[3:] if bom else data
    return source.decode('utf-8').replace('\r\n', '\n'), bom, b'\r\n' in source


def _encode(source: str, bom: bool, crlf: bool) -> bytes:
    if crlf:
        source = source.replace('\n', '\r\n')
    return (b'\xef\xbb\xbf' if bom else b'') + source.encode('utf-8')


def _check_prior(root: Path) -> None:
    for rel, expected in PRIOR_SHA.items():
        path = root / rel
        if not path.is_file() or _lf_digest(path.read_bytes()) != expected:
            raise InstallationError('10차 수정 완료 상태의 검증 파일이 예상과 다릅니다: ' + rel)


def _mapping_pairs(source: str) -> list[tuple[str, str]]:
    tree = ast.parse(source)
    values = [node.value for node in tree.body
              if isinstance(node, ast.AnnAssign)
              and isinstance(node.target, ast.Name)
              and node.target.id == 'CREATE_ACTION_BY_TAG']
    if len(values) != 1 or not isinstance(values[0], ast.Dict):
        raise InstallationError('태그 매핑 딕셔너리 구조가 달라졌습니다.')
    pairs = []
    for key, value in zip(values[0].keys, values[0].values):
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)
                and isinstance(value, ast.Constant) and isinstance(value.value, str)):
            raise InstallationError('동적 태그/액션 등록이 발견되어 중단합니다.')
        pairs.append((key.value, value.value))
    if len(pairs) != len({key for key, _ in pairs}):
        raise InstallationError('기존 레지스트리에 태그 중복이 있습니다. 중단합니다.')
    return pairs


def _validate_registry(source: str, installed: bool) -> None:
    pairs = _mapping_pairs(source)
    expected_count = 72 if installed else 69
    if len(pairs) != expected_count:
        raise InstallationError(f'등록 태그 개수 불일치: {len(pairs)} (예상 {expected_count}).')
    mapping = dict(pairs)
    for tag, action in EXPECTED_EXISTING.items():
        if mapping.get(tag) != action:
            raise InstallationError('기존 변환 태그 연결 변경 감지: ' + tag)
    for tag, action in EXPECTED_NEW.items():
        if installed and mapping.get(tag) != action:
            raise InstallationError('11차 신규 변환 태그 연결 불일치: ' + tag)
        if not installed and tag in mapping:
            raise InstallationError('신규 등록 대상이 이미 연결되어 있습니다: ' + tag)


def _validate_rules(source: str) -> None:
    tree = ast.parse(source)
    rules = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in (
                        'SYNTAX_TAG_RULES', 'CONCEPT_TAG_RULES'):
                    if not isinstance(node.value, ast.Dict):
                        raise InstallationError('태그 규칙 구조 변경')
                    rules[target.id] = {key.value for key in node.value.keys
                                        if isinstance(key, ast.Constant)}
    if len(rules.get('SYNTAX_TAG_RULES', set())) != 61 or len(rules.get('CONCEPT_TAG_RULES', set())) != 41:
        raise InstallationError('태그 규칙 61+41개 기준과 다른 프로젝트 버전입니다.')
    if not set(EXPECTED_NEW) <= rules['SYNTAX_TAG_RULES']:
        raise InstallationError('11차 대상 문법 태그가 실제 태그 규칙에 없습니다.')


def _replace_once(source: str, anchor: str, insert: str, marker: str,
                  label: str) -> str:
    if marker in source:
        if source.count(insert) != 1:
            raise InstallationError(label + ': 11차 코드 부분 적용 또는 수동 변경 감지')
        return source
    if source.count(anchor) != 1:
        raise InstallationError(label + ': 기준 삽입 위치를 정확히 찾지 못했습니다.')
    return source.replace(anchor, insert + anchor, 1)


def _patch_registry(source: str) -> str:
    marker = 'CAPSTONE_UNMAPPED_BATCH11_REGISTRY_V1'
    if marker in source:
        if source.count(REGISTRY_INSERT) != 1:
            raise InstallationError('11차 레지스트리 부분 적용 감지')
        return source
    if source.count(REGISTRY_ANCHOR) != 1:
        raise InstallationError('태그 딕셔너리 선언 위치를 찾을 수 없습니다.')
    return source.replace(REGISTRY_ANCHOR, REGISTRY_ANCHOR + REGISTRY_INSERT, 1)


def _patch_dispatch(source: str) -> str:
    # Check both insertions before changing either, to reject partial installs.
    markers = ('CAPSTONE_UNMAPPED_BATCH11_IMPORT_V1', 'CAPSTONE_UNMAPPED_BATCH11_MAP_V1')
    present = [m in source for m in markers]
    if any(present):
        if not all(present) or source.count(DISPATCH_IMPORT) != 1 or source.count(DISPATCH_MAP_INSERT) != 1:
            raise InstallationError('11차 변환 실행기 부분 적용 감지')
        return source
    if source.count(DISPATCH_ANCHOR) != 1 or source.count(DISPATCH_MAP_ANCHOR) != 1:
        raise InstallationError('변환 실행기 삽입 위치가 달라졌습니다.')
    source = source.replace(DISPATCH_ANCHOR, DISPATCH_IMPORT + DISPATCH_ANCHOR, 1)
    return source.replace(DISPATCH_MAP_ANCHOR, DISPATCH_MAP_ANCHOR + DISPATCH_MAP_INSERT, 1)


def _patch_plan(source: str) -> str:
    return _replace_once(source, PLAN_ANCHOR, PLAN_INSERT,
                         'CAPSTONE_UNMAPPED_BATCH11_PLAN_V1', '스타일 변환 계획')


def preflight(root: Path) -> list[Change]:
    root = root.resolve()
    if not (root / '.git').is_dir() or not (root / 'backend/app/services').is_dir():
        raise InstallationError('capstone_main 프로젝트 최상위 폴더에서 실행해 주세요.')
    _check_prior(root)
    rules = root / RULES
    if not rules.is_file():
        raise InstallationError('기존 태그 규칙 파일 누락')
    _validate_rules(_decode(rules.read_bytes())[0])

    changes: list[Change] = []
    existing = (
        (REGISTRY, _patch_registry),
        (DISPATCH, _patch_dispatch),
        (PLAN, _patch_plan),
    )
    for rel, patcher in existing:
        path = root / rel
        if not path.is_file():
            raise InstallationError('기존 파일 누락: ' + rel)
        original = path.read_bytes()
        source, bom, crlf = _decode(original)
        if rel == REGISTRY:
            _validate_registry(source, 'CAPSTONE_UNMAPPED_BATCH11_REGISTRY_V1' in source)
        if rel == DISPATCH:
            if ('CAPSTONE_UNMAPPED_BATCH9_V1' not in source
                    or 'CAPSTONE_UNMAPPED_BATCH10_V1' not in source):
                raise InstallationError('9~10차 변환기 실행기 기준과 다릅니다.')
        if rel == PLAN:
            if ('CAPSTONE_UNMAPPED_BATCH9_V1' not in source
                    or 'CAPSTONE_UNMAPPED_BATCH10_V1' not in source):
                raise InstallationError('9~10차 변환 계획 기준과 다릅니다.')
        updated = patcher(source)
        ast.parse(updated, filename=rel)
        if rel == REGISTRY:
            _validate_registry(updated, True)
        if updated != source:
            changes.append(Change(path, original, _encode(updated, bom, crlf)))

    for rel, payload_name in NEW.items():
        source = PAYLOAD_DIR / payload_name
        target = root / rel
        if not source.is_file():
            raise InstallationError('신규 패키지 구성 파일 누락: ' + payload_name)
        content = source.read_bytes()
        if sha256(content).hexdigest() != PAYLOAD_SHA[payload_name]:
            raise InstallationError('신규 패키지 해시 오류: ' + payload_name)
        ast.parse(content.decode('utf-8'), filename=payload_name)
        if target.exists():
            if not target.is_file() or _lf_digest(target.read_bytes()) != _lf_digest(content):
                raise InstallationError('기존 동명 파일 변경 감지. 덮어쓰지 않음: ' + rel)
        else:
            changes.append(Change(target, None, content))
    return changes


def _write_atomic(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='wb', dir=target.parent,
                                     prefix='.capstone_batch11_', suffix='.tmp',
                                     delete=False) as handle:
        path = Path(handle.name)
        handle.write(content)
    try:
        os.replace(path, target)
    finally:
        path.unlink(missing_ok=True)


def install(root: Path) -> None:
    root = root.resolve()
    changes = preflight(root)
    if not changes:
        print('11차 패치 이미 설치됨: 변경할 파일이 없습니다.')
        return
    backup = root / '.git' / 'capstone_batch11_backups' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup.mkdir(parents=True, exist_ok=False)
    for change in changes:
        if change.old is not None:
            backup_path = backup / change.path.relative_to(root)
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            backup_path.write_bytes(change.old)
    applied: list[Change] = []
    try:
        for change in changes:
            if change.old is None and change.path.exists():
                raise InstallationError('사전 검사 후 동명 신규 파일 발생: ' + str(change.path))
            if change.old is not None and change.path.read_bytes() != change.old:
                raise InstallationError('사전 검사 후 기존 파일 변경 감지: ' + str(change.path))
            _write_atomic(change.path, change.new)
            applied.append(change)
        if preflight(root):
            raise InstallationError('설치 후 검사 실패: 미적용 변경이 남았습니다.')
    except Exception as exc:
        for change in reversed(applied):
            try:
                if change.old is None:
                    change.path.unlink(missing_ok=True)
                else:
                    _write_atomic(change.path, change.old)
            except OSError:
                pass
        raise InstallationError('11차 설치 오류, 기존 파일 복원 시도: ' + str(exc)) from exc
    print(f'11차 설치 완료: {len(changes)}개 파일 수정/추가. 백업: {backup}')
    print('frontend, 스타일 저장 방식, 주석 제거, 기존 1~10차 변환기는 변경하지 않았습니다.')


def main() -> int:
    p = argparse.ArgumentParser(description='11차 신규 자동 변환 태그 안전 설치')
    p.add_argument('--check', action='store_true')
    p.add_argument('--root', type=Path, default=Path.cwd())
    args = p.parse_args()
    try:
        if args.check:
            changes = preflight(args.root)
            print(f'설치 전 검사 통과: {len(changes)}개 파일 수정/추가 예정')
            for c in changes:
                print(' -', c.path.relative_to(args.root.resolve()))
            return 0
        install(args.root)
        return 0
    except (InstallationError, OSError, ValueError, UnicodeError, SyntaxError) as exc:
        print('11차 설치 중단:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
