"""Install Batch 12 after the user-verified a45accd (Batch 11) revision.

Commands from repository root:
    python backend/tools/install_unmapped_batch12.py --check
    python backend/tools/install_unmapped_batch12.py

Preflight validates the expected 72-link registry and known Batch 11 anchors,
rejects unexpected collisions/partial installs, checks payload SHA256, and
preserves BOM and line endings. Existing files are saved under .git before any
write; detected write failures trigger rollback. Re-running is idempotent.
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
SOURCE_DIR = Path(__file__).resolve().parent / 'unmapped_batch12_payload'
NEW = {
    'backend/app/services/improvement/safe_unmapped_patterns_batch12_service.py':
        'safe_unmapped_patterns_batch12_service.py.source',
    'backend/tests/test_style_unmapped_patterns_batch12.py':
        'test_style_unmapped_patterns_batch12.py.source',
    'backend/tests/test_style_unmapped_patterns_batch12_integration.py':
        'test_style_unmapped_patterns_batch12_integration.py.source',
    'backend/tools/audit_transform_three_patterns_batch12.py':
        'audit_transform_three_patterns_batch12.py.source',
}
PAYLOAD_SHA256 = {
    'safe_unmapped_patterns_batch12_service.py.source':
        '997ba0e415ae9ff8a855fa7409f1f3e4d8b795738c9676e38c944956fdae1a48',
    'test_style_unmapped_patterns_batch12.py.source':
        '1e19f53f710a46a2981323c3525d8fdb2558eb8610e71f2748900b017d1c2566',
    'test_style_unmapped_patterns_batch12_integration.py.source':
        '42d54392eca917dbd5e940f296929c66aadd4fb4eeed34705b49029513a8708b',
    'audit_transform_three_patterns_batch12.py.source':
        'aee5593a3f3eca6cf634bd8aadab768b088542592e9237d2a3436b2d73658836',
}

MAPPING = {
    'continue문': 'create_safe_guard_continue',
    '식별 비교': 'create_safe_literal_identity',
    '산술 연산': 'create_safe_arithmetic_expression',
}
REGISTRY_ANCHOR = 'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
REGISTRY_INSERT = '''    # CAPSTONE_UNMAPPED_BATCH12_REGISTRY_V1: three verified constrained tags.
    "continue문": "create_safe_guard_continue",
    "식별 비교": "create_safe_literal_identity",
    "산술 연산": "create_safe_arithmetic_expression",
'''
DISPATCH_ANCHOR = 'def _get_transform_function(action: str):\n'
DISPATCH_IMPORT = '''# CAPSTONE_UNMAPPED_BATCH12_IMPORT_V1
from app.services.improvement.safe_unmapped_patterns_batch12_service import (
    transform_to_safe_guard_continue_style,
    transform_to_safe_literal_identity_style,
)

'''
DISPATCH_MAP_ANCHOR = '    action_map = {\n'
DISPATCH_MAP_INSERT = '''        # CAPSTONE_UNMAPPED_BATCH12_MAP_V1
        "create_safe_guard_continue": transform_to_safe_guard_continue_style,
        "create_safe_literal_identity": transform_to_safe_literal_identity_style,
'''
PLAN_ANCHOR = '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n'
PLAN_INSERT = '''    # CAPSTONE_UNMAPPED_BATCH12_PLAN_V1: infer preference only from preexisting
    # persisted metrics. No saved style/schema/frontend modifications.
    saved_b12 = _get_style_metrics(diff)
    target_b12 = _get_target_metrics(diff)
    safe_prefs_b12 = (
        ("continue문", "create_safe_guard_continue", "continue_count",
         ("loop_count", "if_count")),
        ("식별 비교", "create_safe_literal_identity", "identity_compare_count",
         ("compare_count", "none_count")),
        ("산술 연산", "create_safe_arithmetic_expression", "bin_op_count",
         ("call_count", "attribute_count", "import_count")),
    )
    for tag_b12, action_b12, preferred_b12, evidence_b12 in safe_prefs_b12:
        if (_metric_count(saved_b12, preferred_b12) > 0
                and _metric_count(target_b12, preferred_b12) == 0
                and all(_metric_count(target_b12, key) > 0 for key in evidence_b12)
                and not any(item.get("action") == action_b12 for item in actions)):
            actions.append({
                "tag": tag_b12,
                "action": action_b12,
                "reason": "기존 저장 메트릭의 스타일 선호가 확인된 안전한 국소 패턴만 변환합니다.",
            })

'''


class InstallationError(Exception):
    pass


@dataclass(frozen=True)
class Change:
    path: Path
    before: bytes | None
    after: bytes


def _decode(data: bytes) -> tuple[str, bool, bool]:
    bom = data.startswith(b'\xef\xbb\xbf')
    remainder = data[3:] if bom else data
    return remainder.decode('utf-8').replace('\r\n', '\n'), bom, b'\r\n' in remainder


def _encode(source: str, bom: bool, crlf: bool) -> bytes:
    if crlf:
        source = source.replace('\n', '\r\n')
    return (b'\xef\xbb\xbf' if bom else b'') + source.encode('utf-8')


def _pairs(source: str) -> list[tuple[str, str]]:
    tree = ast.parse(source)
    entries = [n.value for n in tree.body
               if isinstance(n, ast.AnnAssign)
               and isinstance(n.target, ast.Name)
               and n.target.id == 'CREATE_ACTION_BY_TAG']
    if len(entries) != 1 or not isinstance(entries[0], ast.Dict):
        raise InstallationError('레지스트리 선언 구조가 예상과 다릅니다.')
    pairs = []
    for k, v in zip(entries[0].keys, entries[0].values):
        if not (isinstance(k, ast.Constant) and isinstance(k.value, str)
                and isinstance(v, ast.Constant) and isinstance(v.value, str)):
            raise InstallationError('동적 태그 등록 구조는 안전하게 수정할 수 없습니다.')
        pairs.append((k.value, v.value))
    if len(pairs) != len({k for k, _ in pairs}):
        raise InstallationError('중복 태그가 확인되었습니다. 설치를 중단합니다.')
    return pairs


def _validate_rules(source: str) -> None:
    tree = ast.parse(source)
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('SYNTAX_TAG_RULES', 'CONCEPT_TAG_RULES'):
                    if not isinstance(node.value, ast.Dict):
                        raise InstallationError('태그 규칙 사전 형식이 다릅니다.')
                    found[target.id] = {x.value for x in node.value.keys if isinstance(x, ast.Constant)}
    if len(found.get('SYNTAX_TAG_RULES', [])) != 61 or len(found.get('CONCEPT_TAG_RULES', [])) != 41:
        raise InstallationError('기존 규칙 61+41개와 다른 버전입니다.')
    if not set(MAPPING).issubset(found['SYNTAX_TAG_RULES']):
        raise InstallationError('12차 대상 태그가 문법 규칙에 등록되어 있지 않습니다.')


def _validate_base(source: str, installed: bool) -> None:
    pairs = _pairs(source)
    expected = 75 if installed else 72
    if len(pairs) != expected:
        raise InstallationError(f'등록 개수 불일치: {len(pairs)} (예상 {expected}).')
    mapping = dict(pairs)
    previous = {
        'len 사용': 'create_safe_literal_len',
        'zip 사용': 'create_safe_literal_zip',
        '슬라이싱 사용': 'create_safe_list_slice',
        'enumerate 사용': 'create_safe_enumerate',
        'range 사용': 'create_safe_literal_range',
        '함수 호출 중심 구조': 'create_safe_operator_call',
    }
    for tag, action in previous.items():
        if mapping.get(tag) != action:
            raise InstallationError('기존 액션 매핑이 변경되었습니다: ' + tag)
    for tag, action in MAPPING.items():
        if (installed and mapping.get(tag) != action) or (not installed and tag in mapping):
            raise InstallationError('12차 태그 연결이 예상 상태와 다릅니다: ' + tag)


def _replace_once(source: str, anchor: str, insert: str, marker: str) -> str:
    if marker in source:
        if source.count(insert) != 1:
            raise InstallationError(f'{marker}: 일부 적용/수동 변경이 확인되었습니다.')
        return source
    if source.count(anchor) != 1:
        raise InstallationError(f'{marker}: 삽입 위치가 예상과 다릅니다.')
    return source.replace(anchor, insert + anchor, 1)


def _patch_registry(source: str) -> str:
    if 'CAPSTONE_UNMAPPED_BATCH12_REGISTRY_V1' in source:
        if source.count(REGISTRY_INSERT) != 1:
            raise InstallationError('12차 레지스트리 부분 적용 상태입니다.')
        return source
    if source.count(REGISTRY_ANCHOR) != 1:
        raise InstallationError('레지스트리 딕셔너리 선언이 다릅니다.')
    return source.replace(REGISTRY_ANCHOR, REGISTRY_ANCHOR + REGISTRY_INSERT, 1)


def _patch_dispatch(source: str) -> str:
    source = _replace_once(source, DISPATCH_ANCHOR, DISPATCH_IMPORT,
                           'CAPSTONE_UNMAPPED_BATCH12_IMPORT_V1')
    if 'CAPSTONE_UNMAPPED_BATCH12_MAP_V1' in source:
        if source.count(DISPATCH_MAP_INSERT) != 1:
            raise InstallationError('12차 실행 액션 맵 부분 적용 상태입니다.')
        return source
    if source.count(DISPATCH_MAP_ANCHOR) != 1:
        raise InstallationError('실행 액션 맵 삽입 위치가 다릅니다.')
    return source.replace(DISPATCH_MAP_ANCHOR,
                          DISPATCH_MAP_ANCHOR + DISPATCH_MAP_INSERT, 1)


def _patch_plan(source: str) -> str:
    return _replace_once(source, PLAN_ANCHOR, PLAN_INSERT,
                         'CAPSTONE_UNMAPPED_BATCH12_PLAN_V1')


def preflight(root: Path) -> list[Change]:
    root = root.resolve()
    if not (root / '.git').exists() or not (root / 'backend/app/services').is_dir():
        raise InstallationError('capstone_main 프로젝트의 최상위 폴더에서 실행해야 합니다.')
    required = (REGISTRY, DISPATCH, PLAN, RULES)
    if not all((root / x).is_file() for x in required):
        raise InstallationError('백엔드 핵심 파일이 누락되었습니다.')
    _validate_rules(_decode((root / RULES).read_bytes())[0])
    sources = {x: _decode((root / x).read_bytes())[0] for x in required[:3]}
    markers = (
        'CAPSTONE_UNMAPPED_BATCH12_REGISTRY_V1' in sources[REGISTRY],
        'CAPSTONE_UNMAPPED_BATCH12_IMPORT_V1' in sources[DISPATCH],
        'CAPSTONE_UNMAPPED_BATCH12_MAP_V1' in sources[DISPATCH],
        'CAPSTONE_UNMAPPED_BATCH12_PLAN_V1' in sources[PLAN],
    )
    if any(markers) and not all(markers):
        raise InstallationError('12차 핵심 파일이 부분 적용 상태여서 자동 덮어쓰지 않습니다.')
    installed = all(markers)
    _validate_base(sources[REGISTRY], installed)
    if not ('CAPSTONE_UNMAPPED_BATCH11_IMPORT_V1' in sources[DISPATCH]
            and 'CAPSTONE_UNMAPPED_BATCH11_MAP_V1' in sources[DISPATCH]
            and 'CAPSTONE_UNMAPPED_BATCH11_PLAN_V1' in sources[PLAN]):
        raise InstallationError('GitHub a45accd의 11차 설치 완료 기준이 아닙니다.')
    if sources[DISPATCH].count('"create_safe_arithmetic_expression": transform_operator_call_to_arithmetic') != 1:
        raise InstallationError('기존 산술 연산 변환기의 함수 연결이 달라졌습니다.')
    changes: list[Change] = []
    for rel, update in ((REGISTRY, _patch_registry),
                        (DISPATCH, _patch_dispatch),
                        (PLAN, _patch_plan)):
        path = root / rel
        original = path.read_bytes()
        source, bom, crlf = _decode(original)
        updated = update(source)
        ast.parse(updated, filename=rel)
        if rel == REGISTRY:
            _validate_base(updated, True)
        if updated != source:
            changes.append(Change(path, original, _encode(updated, bom, crlf)))

    for rel, payload_name in NEW.items():
        path = SOURCE_DIR / payload_name
        target = root / rel
        if not path.is_file():
            raise InstallationError('패키지 파일 누락: ' + payload_name)
        content = path.read_bytes()
        if sha256(content).hexdigest() != PAYLOAD_SHA256[payload_name]:
            raise InstallationError('패키지 파일 해시 불일치: ' + payload_name)
        ast.parse(content.decode('utf-8'), filename=rel)
        if target.exists():
            if not target.is_file() or sha256(target.read_bytes()).hexdigest() != sha256(content).hexdigest():
                raise InstallationError('같은 경로에 다른 파일이 있습니다: ' + rel)
        else:
            changes.append(Change(target, None, content))
    return changes


def _atomic_write(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='wb', dir=target.parent,
                                     prefix='.batch12_', suffix='.tmp',
                                     delete=False) as handle:
        tmp = Path(handle.name)
        handle.write(content)
    try:
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def install(root: Path) -> None:
    root = root.resolve()
    changes = preflight(root)
    if not changes:
        print('12차 패치 이미 설치됨: 변경할 파일 없음.')
        return
    backup = root / '.git' / 'capstone_batch12_backups' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup.mkdir(parents=True, exist_ok=False)
    for change in changes:
        if change.before is not None:
            dest = backup / change.path.relative_to(root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(change.before)
    applied: list[Change] = []
    try:
        for change in changes:
            if change.before is None and change.path.exists():
                raise InstallationError('새 파일 경로가 설치 중 생성됨: ' + str(change.path))
            if change.before is not None and change.path.read_bytes() != change.before:
                raise InstallationError('기존 파일이 설치 중 변경됨: ' + str(change.path))
            _atomic_write(change.path, change.after)
            applied.append(change)
        if preflight(root):
            raise InstallationError('설치 후 검증 실패: 미적용 항목 존재')
    except Exception as error:
        for change in reversed(applied):
            try:
                if change.before is None:
                    change.path.unlink(missing_ok=True)
                else:
                    _atomic_write(change.path, change.before)
            except OSError:
                pass
        raise InstallationError('설치 오류, 기존 파일 복원 시도: ' + str(error)) from error
    print(f'12차 설치 완료: {len(changes)}개 파일 변경. 백업: {backup}')
    print('기존 1~11차 변환 코드, 프론트엔드, 스타일 저장 포맷은 변경하지 않았습니다.')


def main() -> int:
    p = argparse.ArgumentParser(description='12차 자동변환 태그 설치')
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    try:
        if args.check:
            changes = preflight(args.root)
            print(f'12차 설치 전 검사 통과: {len(changes)}개 파일 변경 예정')
            for change in changes:
                print(' -', change.path.relative_to(args.root.resolve()))
        else:
            install(args.root)
        return 0
    except (InstallationError, OSError, SyntaxError, ValueError, UnicodeError) as error:
        print('12차 설치 중단:', error, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
