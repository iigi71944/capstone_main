"""Install Batch 13 over the GitHub b89bcc8 snapshot (12 batches complete).

Run from repository root:
  python backend/tools/install_unmapped_batch13.py --check
  python backend/tools/install_unmapped_batch13.py

The installer is fail-closed: verifies exact baseline Git blob hashes, existing
links and 61+41 tag definitions, all payload checksums, AST parseability,
non-overwriting new files, and all-or-none markers. It stores originals under
.git and restores edited files on detected installation errors. CRLF/BOM are
preserved and repeat installation is idempotent.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from datetime import datetime
import hashlib
import os
from pathlib import Path
import sys
import tempfile

REGISTRY = 'backend/app/services/style_tag_transform_map_service.py'
DISPATCH = 'backend/app/services/style_apply_service.py'
PLAN = 'backend/app/services/style_transform_plan_service.py'
TEST12 = 'backend/tests/test_style_unmapped_patterns_batch12_integration.py'
AUDIT12 = 'backend/tools/audit_transform_three_patterns_batch12.py'
RULES = 'backend/app/services/tag_rule_service.py'

BASE_BLOBS = {
    REGISTRY: 'f6d99fd7c1537dba89581645820766cf797befd0',
    DISPATCH: '99e39562a30fce310d4323f9b72149ecc96dc019',
    PLAN: 'f3f5a50ba4030eb2275cc6a63e5ae4f6187556c2',
    TEST12: '48319be1fcd663f983337cd4749762cd987ec1b4',
    AUDIT12: '591be954a68fd398d1c9abcb255b2e07dfb9953b',
}

PAYLOAD_DIR = Path(__file__).resolve().parent / 'unmapped_batch13_payload'
NEW = {
    'backend/app/services/improvement/safe_unmapped_patterns_batch13_service.py':
        'safe_unmapped_patterns_batch13_service.py.source',
    'backend/tests/test_style_unmapped_patterns_batch13.py':
        'test_style_unmapped_patterns_batch13.py.source',
    'backend/tests/test_style_unmapped_patterns_batch13_integration.py':
        'test_style_unmapped_patterns_batch13_integration.py.source',
    'backend/tools/audit_transform_three_patterns_batch13.py':
        'audit_transform_three_patterns_batch13.py.source',
}
PAYLOAD_SHA256 = {
    'audit_transform_three_patterns_batch13.py.source': 'ef7a732eb506730b7d67d595afae1ddab44e11d4dcfe47519277bf8c1ddb3c58',
    'safe_unmapped_patterns_batch13_service.py.source': 'e64826f3cbf76db33085efb1c639e77ce6cef9fa0ca09902f0fa9d311e54f24b',
    'test_style_unmapped_patterns_batch13.py.source': 'ca816456ace79de9d51aae7e9aa56b2c35e660300ea4c6cfb4978f69124659bf',
    'test_style_unmapped_patterns_batch13_integration.py.source': 'c827888e13d70877761cd2f4d80a0eddecff974aa26c0b0820720d106cce3751',
}

NEW_ACTIONS = {
    '문자열 리터럴': 'create_safe_string_literal',
    '숫자 리터럴': 'create_safe_number_literal',
    '불리언 리터럴': 'create_safe_boolean_literal',
}
PRIOR_ACTIONS = {
    'continue문': 'create_safe_guard_continue',
    '식별 비교': 'create_safe_literal_identity',
    '산술 연산': 'create_safe_arithmetic_expression',
    'len 사용': 'create_safe_literal_len',
    'zip 사용': 'create_safe_literal_zip',
    '슬라이싱 사용': 'create_safe_list_slice',
    'enumerate 사용': 'create_safe_enumerate',
}

REGISTRY_INSERT = '''    # CAPSTONE_UNMAPPED_BATCH13_REGISTRY_V1: literal builtin calls only.
    "문자열 리터럴": "create_safe_string_literal",
    "숫자 리터럴": "create_safe_number_literal",
    "불리언 리터럴": "create_safe_boolean_literal",
'''
IMPORT_INSERT = '''# CAPSTONE_UNMAPPED_BATCH13_IMPORT_V1
from app.services.improvement.safe_unmapped_patterns_batch13_service import (
    transform_to_safe_string_literal_style,
    transform_to_safe_number_literal_style,
    transform_to_safe_boolean_literal_style,
)

'''
DISPATCH_INSERT = '''        # CAPSTONE_UNMAPPED_BATCH13_MAP_V1
        "create_safe_string_literal": transform_to_safe_string_literal_style,
        "create_safe_number_literal": transform_to_safe_number_literal_style,
        "create_safe_boolean_literal": transform_to_safe_boolean_literal_style,
'''
PLAN_INSERT = '''    # CAPSTONE_UNMAPPED_BATCH13_PLAN_V1: use existing persisted metrics only.
    # No changes to the 19 saved syntax preferences, APIs or frontend.
    saved_b13 = _get_style_metrics(diff)
    target_b13 = _get_target_metrics(diff)
    for tag_b13, metric_b13, action_b13 in (
        ("문자열 리터럴", "string_literal_count", "create_safe_string_literal"),
        ("숫자 리터럴", "number_literal_count", "create_safe_number_literal"),
        ("불리언 리터럴", "boolean_literal_count", "create_safe_boolean_literal"),
    ):
        if (_metric_count(saved_b13, metric_b13) > 0
                and _metric_count(target_b13, metric_b13) == 0
                and _metric_count(target_b13, "call_count") > 0
                and not any(item.get("action") == action_b13 for item in actions)):
            actions.append({
                "tag": tag_b13,
                "action": action_b13,
                "reason": "저장된 기존 리터럴 메트릭을 반영하되 기본 내장 함수의 상수 호출만 변환합니다.",
            })

'''
PLAN_GUARD_ANCHOR = '''        if action is None:
            compare_only.append(tag_name)
            continue
'''
PLAN_GUARD_INSERT = '''
        # CAPSTONE_UNMAPPED_BATCH13_METRIC_ONLY_V1: never select these actions
        # from a missing-tag record alone; only the gated metrics above may.
        if action in {
            "create_safe_string_literal",
            "create_safe_number_literal",
            "create_safe_boolean_literal",
        }:
            continue
'''
TEST12_OLD = '''        self.assertEqual(len(keys), 75)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(mapping.COMPARE_ONLY_TAGS), 27)'''
TEST12_NEW = '''        # CAPSTONE_UNMAPPED_BATCH13_COMPAT12_V1: retain Batch 12 baseline.
        self.assertGreaterEqual(len(keys), 75)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), set(mapping.CREATE_ACTION_BY_TAG))
        all_tags = set(mapping.SYNTAX_TAG_RULES) | set(mapping.CONCEPT_TAG_RULES)
        self.assertTrue(set(keys) <= all_tags)
        self.assertEqual(mapping.COMPARE_ONLY_TAGS, all_tags - set(keys))
        self.assertEqual(len(keys) + len(mapping.COMPARE_ONLY_TAGS), len(all_tags))'''
AUDIT12_OLD = '''        and summary['linked'] == 75
        and summary['compare_only'] == 27
        and summary['by_status']['three_patterns_verified'] == 75
        and summary['by_status']['three_patterns_not_yet_proven'] == 0'''
AUDIT12_NEW = '''        # CAPSTONE_UNMAPPED_BATCH13_COMPAT_AUDIT12_V1: earlier triplets remain verified.
        and summary['linked'] >= 75
        and summary['compare_only'] == summary['tags'] - summary['linked']
        and summary['by_status']['three_patterns_verified'] == 75
        and summary['by_status']['three_patterns_not_yet_proven'] == summary['linked'] - 75'''


class InstallationError(Exception):
    pass


@dataclass(frozen=True)
class Change:
    path: Path
    original: bytes | None
    replacement: bytes


def _normalize(data: bytes) -> bytes:
    return data.removeprefix(b'\xef\xbb\xbf').replace(b'\r\n', b'\n')


def _git_blob(data: bytes) -> str:
    normalized = _normalize(data)
    return hashlib.sha1(b'blob ' + str(len(normalized)).encode('ascii')
                        + b'\0' + normalized).hexdigest()


def _decode(data: bytes) -> tuple[str, bool, bool]:
    bom = data.startswith(b'\xef\xbb\xbf')
    rest = data[3:] if bom else data
    return rest.decode('utf-8').replace('\r\n', '\n'), bom, b'\r\n' in rest


def _encode(code: str, bom: bool, crlf: bool) -> bytes:
    if crlf:
        code = code.replace('\n', '\r\n')
    return (b'\xef\xbb\xbf' if bom else b'') + code.encode('utf-8')


def _parse_registry(code: str) -> list[tuple[str, str]]:
    tree = ast.parse(code)
    registrations = [node.value for node in tree.body
                     if isinstance(node, ast.AnnAssign)
                     and isinstance(node.target, ast.Name)
                     and node.target.id == 'CREATE_ACTION_BY_TAG']
    if len(registrations) != 1 or not isinstance(registrations[0], ast.Dict):
        raise InstallationError('예상 레지스트리 딕셔너리를 찾을 수 없습니다.')
    result = []
    for k, v in zip(registrations[0].keys, registrations[0].values):
        if not (isinstance(k, ast.Constant) and isinstance(k.value, str)
                and isinstance(v, ast.Constant) and isinstance(v.value, str)):
            raise InstallationError('레지스트리 형식이 예상과 다릅니다.')
        result.append((k.value, v.value))
    if len(result) != len({k for k, _ in result}):
        raise InstallationError('레지스트리 중복 키가 있습니다. 중단합니다.')
    return result


def _validate_registry(code: str, installed: bool) -> None:
    pairs = _parse_registry(code)
    expected = 78 if installed else 75
    if len(pairs) != expected:
        raise InstallationError(f'연결 태그 수가 예상과 다릅니다: {len(pairs)} / {expected}')
    mapping = dict(pairs)
    for tag, action in PRIOR_ACTIONS.items():
        if mapping.get(tag) != action:
            raise InstallationError('12차 이전 연결 변경 감지: ' + tag)
    for tag, action in NEW_ACTIONS.items():
        if installed and mapping.get(tag) != action:
            raise InstallationError('13차 연결 불일치: ' + tag)
        if not installed and tag in mapping:
            raise InstallationError('13차 대상 태그가 이미 등록되어 있습니다: ' + tag)


def _validate_rules(code: str) -> None:
    tree = ast.parse(code)
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('SYNTAX_TAG_RULES', 'CONCEPT_TAG_RULES'):
                    if not isinstance(node.value, ast.Dict):
                        raise InstallationError('태그 규칙 딕셔너리 형식이 예상과 다릅니다.')
                    found[target.id] = {k.value for k in node.value.keys
                                        if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    if len(found.get('SYNTAX_TAG_RULES', set())) != 61 or len(found.get('CONCEPT_TAG_RULES', set())) != 41:
        raise InstallationError('기존 태그 61+41개 기준과 다릅니다.')
    if not set(NEW_ACTIONS) <= found['SYNTAX_TAG_RULES']:
        raise InstallationError('13차 문법 태그가 정의되지 않았습니다.')


def _replace_once(code: str, anchor: str, insert: str, marker: str,
                  *, after: bool = False) -> str:
    if marker in code:
        if code.count(insert) != 1:
            raise InstallationError(f'{marker}: 부분 적용 또는 수동 변경 감지')
        return code
    if code.count(anchor) != 1:
        raise InstallationError(f'{marker}: 정확한 삽입 위치가 없습니다.')
    return code.replace(anchor, anchor + insert if after else insert + anchor, 1)


def _patch_registry(code: str) -> str:
    return _replace_once(code, 'CREATE_ACTION_BY_TAG: dict[str, str] = {\n',
                         REGISTRY_INSERT, 'CAPSTONE_UNMAPPED_BATCH13_REGISTRY_V1',
                         after=True)


def _patch_dispatch(code: str) -> str:
    code = _replace_once(code, 'def _get_transform_function(action: str):\n',
                         IMPORT_INSERT, 'CAPSTONE_UNMAPPED_BATCH13_IMPORT_V1')
    return _replace_once(code, '    action_map = {\n', DISPATCH_INSERT,
                         'CAPSTONE_UNMAPPED_BATCH13_MAP_V1', after=True)


def _patch_plan(code: str) -> str:
    code = _replace_once(code,
                         '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n',
                         PLAN_INSERT, 'CAPSTONE_UNMAPPED_BATCH13_PLAN_V1')
    return _replace_once(code, PLAN_GUARD_ANCHOR, PLAN_GUARD_INSERT,
                         'CAPSTONE_UNMAPPED_BATCH13_METRIC_ONLY_V1', after=True)


def _swap_once(code: str, old: str, new: str, marker: str) -> str:
    if marker in code:
        if code.count(new) != 1 or old in code:
            raise InstallationError(f'{marker}: 부분 적용 또는 수동 변경 감지')
        return code
    if code.count(old) != 1:
        raise InstallationError(f'{marker}: 기존 검사 위치가 예상과 다릅니다.')
    return code.replace(old, new, 1)


def _patch_test12(code: str) -> str:
    return _swap_once(code, TEST12_OLD, TEST12_NEW,
                      'CAPSTONE_UNMAPPED_BATCH13_COMPAT12_V1')


def _patch_audit12(code: str) -> str:
    return _swap_once(code, AUDIT12_OLD, AUDIT12_NEW,
                      'CAPSTONE_UNMAPPED_BATCH13_COMPAT_AUDIT12_V1')


PATCHES = (
    (REGISTRY, _patch_registry, 'CAPSTONE_UNMAPPED_BATCH13_REGISTRY_V1'),
    (DISPATCH, _patch_dispatch, 'CAPSTONE_UNMAPPED_BATCH13_IMPORT_V1'),
    (PLAN, _patch_plan, 'CAPSTONE_UNMAPPED_BATCH13_PLAN_V1'),
    (TEST12, _patch_test12, 'CAPSTONE_UNMAPPED_BATCH13_COMPAT12_V1'),
    (AUDIT12, _patch_audit12, 'CAPSTONE_UNMAPPED_BATCH13_COMPAT_AUDIT12_V1'),
)


def preflight(root: Path) -> list[Change]:
    root = root.resolve()
    if not (root / '.git').exists() or not (root / 'backend/app/services').is_dir():
        raise InstallationError('capstone_main Git 저장소 최상위 폴더에서 실행해 주세요.')
    if not (root / RULES).is_file():
        raise InstallationError('기존 태그 규칙 파일이 없습니다.')
    _validate_rules(_decode((root / RULES).read_bytes())[0])

    sources = {}
    markers = []
    for rel, _patcher, marker in PATCHES:
        path = root / rel
        if not path.is_file():
            raise InstallationError('기존 파일 누락: ' + rel)
        src = _decode(path.read_bytes())[0]
        sources[rel] = src
        markers.append(marker in src)
    # Dispatcher and plan have paired insertions; detect partial installs.
    markers.append('CAPSTONE_UNMAPPED_BATCH13_MAP_V1' in sources[DISPATCH])
    markers.append('CAPSTONE_UNMAPPED_BATCH13_METRIC_ONLY_V1' in sources[PLAN])
    if any(markers) and not all(markers):
        raise InstallationError('13차 패치가 부분 적용된 상태입니다. 자동 덮어쓰기를 중단합니다.')
    installed = all(markers)
    _validate_registry(sources[REGISTRY], installed)
    if not ('CAPSTONE_UNMAPPED_BATCH12_REGISTRY_V1' in sources[REGISTRY]
            and 'CAPSTONE_UNMAPPED_BATCH12_MAP_V1' in sources[DISPATCH]
            and 'CAPSTONE_UNMAPPED_BATCH12_PLAN_V1' in sources[PLAN]):
        raise InstallationError('12차 패치 완료 기준과 다릅니다.')
    if not installed:
        for rel, expected in BASE_BLOBS.items():
            actual = _git_blob((root / rel).read_bytes())
            if actual != expected:
                raise InstallationError('b89bcc8 기준과 다른 파일 감지: ' + rel
                                        + ' (기존 수정 사항을 덮어쓰지 않습니다.)')

    changes: list[Change] = []
    for rel, patcher, _marker in PATCHES:
        path = root / rel
        original = path.read_bytes()
        code, bom, crlf = _decode(original)
        updated = patcher(code)
        ast.parse(updated, filename=rel)
        if rel == REGISTRY:
            _validate_registry(updated, True)
        if updated != code:
            changes.append(Change(path, original, _encode(updated, bom, crlf)))

    for rel, name in NEW.items():
        source = PAYLOAD_DIR / name
        if not source.is_file():
            raise InstallationError('13차 신규 구성 파일 누락: ' + name)
        content = source.read_bytes()
        if hashlib.sha256(content).hexdigest() != PAYLOAD_SHA256[name]:
            raise InstallationError('13차 신규 구성 파일 무결성 오류: ' + name)
        ast.parse(content.decode('utf-8'), filename=name)
        dest = root / rel
        if dest.exists():
            if not dest.is_file() or _normalize(dest.read_bytes()) != _normalize(content):
                raise InstallationError('기존 동명 파일을 덮어쓰지 않습니다: ' + rel)
        else:
            changes.append(Change(dest, None, content))
    return changes


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent,
                                     prefix='.capstone_batch13_', suffix='.tmp',
                                     delete=False) as handle:
        temp = Path(handle.name)
        handle.write(content)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def install(root: Path) -> None:
    root = root.resolve()
    changes = preflight(root)
    if not changes:
        print('13차 패치 이미 설치됨: 변경할 파일이 없습니다.')
        return
    backup = root / '.git' / 'capstone_batch13_backups' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup.mkdir(parents=True, exist_ok=False)
    for change in changes:
        if change.original is not None:
            bpath = backup / change.path.relative_to(root)
            bpath.parent.mkdir(parents=True, exist_ok=True)
            bpath.write_bytes(change.original)
    applied: list[Change] = []
    try:
        for change in changes:
            if change.original is not None and change.path.read_bytes() != change.original:
                raise InstallationError('설치 도중 기존 파일 변경 감지: ' + str(change.path))
            if change.original is None and change.path.exists():
                raise InstallationError('설치 도중 신규 파일 충돌: ' + str(change.path))
            _write_atomic(change.path, change.replacement)
            applied.append(change)
        if preflight(root):
            raise InstallationError('설치 후 검증 시 미적용 변경이 남았습니다.')
    except Exception as exc:
        for change in reversed(applied):
            try:
                if change.original is None:
                    change.path.unlink(missing_ok=True)
                else:
                    _write_atomic(change.path, change.original)
            except OSError:
                pass
        raise InstallationError('13차 설치 실패, 복원 시도: ' + str(exc)) from exc
    print(f'13차 설치 완료: {len(changes)}개 파일 수정/추가; 백업: {backup}')
    print('프론트엔드, 스타일 저장 형식, 기존 1~12차 변환기는 수정하지 않았습니다.')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        if args.check:
            changes = preflight(args.root)
            print(f'13차 설치 사전 검사 통과: {len(changes)}개 파일 수정/추가 예정')
            for change in changes:
                print(' -', change.path.relative_to(args.root.resolve()))
            return 0
        install(args.root)
        return 0
    except (InstallationError, OSError, ValueError, UnicodeError, SyntaxError, KeyError) as exc:
        print('13차 설치 중단:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
