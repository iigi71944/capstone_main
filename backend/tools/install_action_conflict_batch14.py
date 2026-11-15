"""Install Batch 14 over GitHub commit f6b7d8c (13 batches complete).

Only style_apply_service.py is edited, and three new source/test/audit files
are created. Preflight validates exact baseline Git blob, expected anchors,
new payload hashes and partial-install state. No style schema or frontend edit.

Usage from capstone_main root:
    python backend/tools/install_action_conflict_batch14.py --check
    python backend/tools/install_action_conflict_batch14.py
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

DISPATCH = 'backend/app/services/style_apply_service.py'
EXPECTED_GIT_BLOB = 'a5c0f94ffee193f3a76e134230c99e041bfdfb77'
PAYLOAD_DIR = Path(__file__).resolve().parent / 'batch14_payload'
NEW = {
    'backend/app/services/style_action_conflict_service.py':
        'style_action_conflict_service.py.source',
    'backend/tests/test_style_action_conflict_batch14.py':
        'test_style_action_conflict_batch14.py.source',
    'backend/tools/audit_transform_runtime_batch14.py':
        'audit_transform_runtime_batch14.py.source',
}

# Filled by the packaging step, checked before any file is changed.
PAYLOAD_SHA256 = {
    'style_action_conflict_service.py.source': '024226b3250588b1f91dc3f91e213374803bb696dce28a837d75dfbaa06d262b',
    'test_style_action_conflict_batch14.py.source': '7500f2a2ad3be2311bdb4b03572cc3fba2cd965245670e5c201ad802bd509e73',
    'audit_transform_runtime_batch14.py.source': '4ed75be10d8ac2f98600df6f79a9c43123766d028632f725d046cf73f322bcba',
}

INSERT_IMPORT = '''# CAPSTONE_BATCH14_CONFLICT_IMPORT_V1
from app.services.style_action_conflict_service import mark_reverted_actions
'''
IMPORT_ANCHOR = 'from app.services.style_transform_plan_service import build_transform_plan\n'
START_ANCHOR = '    action_results: list[dict] = []\n'
INSERT_START = '''    # CAPSTONE_BATCH14_CONFLICT_LEDGER_V1: record each attempted action.
    action_snapshots: list[str] = [code]
    action_rules_by_step: list[list[str]] = []
'''
LOOP_ANCHOR = '''    for action_item in transform_plan.get("actions", []):
        transformed_code, action_result = _apply_style_action('''
LOOP_NEW = '''    for action_item in transform_plan.get("actions", []):
        rule_start = len(applied_rules)
        transformed_code, action_result = _apply_style_action('''
AFTER_ANCHOR = '''        action_results.append(action_result)

    # CAPSTONE_LARGE_CODE_SCOPES_V1'''
AFTER_NEW = '''        action_results.append(action_result)
        action_snapshots.append(transformed_code)
        action_rules_by_step.append(applied_rules[rule_start:])

    # CAPSTONE_BATCH14_CONFLICT_RECONCILE_V1: an action can undo earlier
    # actions even when a later action creates a nonempty final difference.
    # Only complete checkpoint reversions are detectable without re-execution.
    if mark_reverted_actions(action_snapshots, action_results, normalize=_normalize_code):
        applied_rules[:] = [
            note
            for index, notes in enumerate(action_rules_by_step)
            if action_results[index].get('status') == 'applied'
            for note in notes
        ]

    # CAPSTONE_LARGE_CODE_SCOPES_V1'''
VERIFIER_ANCHOR = '''        if verification_status == "equivalent" and equivalent is not True:
            verifier_malformed = True
'''
VERIFIER_NEW = '''        if verification_status == "equivalent" and equivalent is not True:
            verifier_malformed = True
        # CAPSTONE_BATCH14_CONTRADICTORY_VERDICT_V1: "different" must not
        # claim equivalence=True (or omit equivalence) in the API result.
        if verification_status == "different" and equivalent is not False:
            verifier_malformed = True
'''
MARKERS = (
    'CAPSTONE_BATCH14_CONFLICT_IMPORT_V1',
    'CAPSTONE_BATCH14_CONFLICT_LEDGER_V1',
    'CAPSTONE_BATCH14_CONFLICT_RECONCILE_V1',
    'CAPSTONE_BATCH14_CONTRADICTORY_VERDICT_V1',
)


class InstallationError(Exception):
    pass


@dataclass(frozen=True)
class Change:
    path: Path
    old: bytes | None
    new: bytes


def _normalized(data: bytes) -> bytes:
    return data.removeprefix(b'\xef\xbb\xbf').replace(b'\r\n', b'\n')


def _git_blob(data: bytes) -> str:
    content = _normalized(data)
    return hashlib.sha1(b'blob ' + str(len(content)).encode('ascii') + b'\0' + content).hexdigest()


def _decode(data: bytes) -> tuple[str, bool, bool]:
    bom = data.startswith(b'\xef\xbb\xbf')
    rest = data[3:] if bom else data
    return rest.decode('utf-8').replace('\r\n', '\n'), bom, b'\r\n' in rest


def _encode(source: str, bom: bool, crlf: bool) -> bytes:
    return (b'\xef\xbb\xbf' if bom else b'') + (
        source.replace('\n', '\r\n') if crlf else source).encode('utf-8')


def _replace_exact(code: str, old: str, new: str, label: str) -> str:
    if code.count(old) != 1:
        raise InstallationError(f'{label}: 삽입 기준이 정확히 한 번 발견되지 않았습니다.')
    return code.replace(old, new, 1)


def _patch(source: str) -> str:
    found = [marker in source for marker in MARKERS]
    if any(found):
        if not all(found) or any(source.count(marker) != 1 for marker in MARKERS):
            raise InstallationError('14차 코드가 부분 적용되었거나 중복되었습니다.')
        # Check expected installed form and reject an unrelated edit.
        if (source.count(INSERT_IMPORT) != 1
                or source.count(INSERT_START) != 1
                or source.count(LOOP_NEW) != 1
                or source.count(AFTER_NEW) != 1
                or source.count(VERIFIER_NEW) != 1):
            raise InstallationError('14차 설치 이후 코드가 변경되어 검증할 수 없습니다.')
        ast.parse(source)
        return source

    updated = _replace_exact(source, IMPORT_ANCHOR, IMPORT_ANCHOR + INSERT_IMPORT, 'import')
    updated = _replace_exact(updated, START_ANCHOR, START_ANCHOR + INSERT_START, 'ledger')
    updated = _replace_exact(updated, LOOP_ANCHOR, LOOP_NEW, 'loop')
    updated = _replace_exact(updated, AFTER_ANCHOR, AFTER_NEW, 'reconcile')
    updated = _replace_exact(updated, VERIFIER_ANCHOR, VERIFIER_NEW, 'verifier')
    ast.parse(updated)
    return updated


def preflight(root: Path) -> list[Change]:
    root = root.resolve()
    if not (root / '.git').is_dir() or not (root / 'backend/app/services').is_dir():
        raise InstallationError('capstone_main 프로젝트 루트에서 실행해야 합니다.')
    target = root / DISPATCH
    if not target.is_file():
        raise InstallationError('기존 스타일 적용 서비스가 없습니다.')
    content = target.read_bytes()
    source, bom, crlf = _decode(content)
    installed = all(marker in source for marker in MARKERS)
    if not installed and _git_blob(content) != EXPECTED_GIT_BLOB:
        raise InstallationError('13차 GitHub f6b7d8c 기준과 코드가 달라 설치를 중단합니다.')
    patched = _patch(source)
    changes = []
    if patched != source:
        changes.append(Change(target, content, _encode(patched, bom, crlf)))

    for rel, payload_name in NEW.items():
        path = PAYLOAD_DIR / payload_name
        destination = root / rel
        if not path.is_file():
            raise InstallationError('배포 파일 누락: ' + payload_name)
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != PAYLOAD_SHA256[payload_name]:
            raise InstallationError('배포 파일 체크섬이 다릅니다: ' + payload_name)
        ast.parse(data.decode('utf-8'), filename=payload_name)
        if destination.exists():
            if not destination.is_file() or _normalized(destination.read_bytes()) != _normalized(data):
                raise InstallationError('다른 내용의 기존 파일을 덮어쓰지 않습니다: ' + rel)
        else:
            changes.append(Change(destination, None, data))

    if installed and changes:
        raise InstallationError('14차 변환기는 설치되어 있지만 신규 파일 일부가 누락된 상태입니다.')
    if not installed and len(changes) != len(NEW) + 1:
        raise InstallationError('14차 구성 파일 중 일부가 이미 존재합니다. 부분 설치 가능성으로 중단합니다.')
    return changes


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent,
                                     prefix='.batch14_', suffix='.tmp', delete=False) as fh:
        tempfile_path = Path(fh.name)
        fh.write(data)
    try:
        os.replace(tempfile_path, path)
    finally:
        tempfile_path.unlink(missing_ok=True)


def install(root: Path) -> None:
    root = root.resolve()
    changes = preflight(root)
    if not changes:
        print('14차 패치가 이미 설치되어 있습니다. 변경 사항이 없습니다.')
        return
    backup = root / '.git' / 'capstone_batch14_backups' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup.mkdir(parents=True, exist_ok=False)
    for change in changes:
        if change.old is not None:
            dest = backup / change.path.relative_to(root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(change.old)
    applied = []
    try:
        for change in changes:
            if change.old is None and change.path.exists():
                raise InstallationError('설치 직전 파일 충돌: ' + str(change.path))
            if change.old is not None and change.path.read_bytes() != change.old:
                raise InstallationError('설치 직전 소스 변경: ' + str(change.path))
            _atomic_write(change.path, change.new)
            applied.append(change)
        if preflight(root):
            raise InstallationError('설치 후 파일 일관성 검증 실패')
    except Exception as error:
        for change in reversed(applied):
            try:
                if change.old is None:
                    change.path.unlink(missing_ok=True)
                else:
                    _atomic_write(change.path, change.old)
            except OSError:
                pass
        raise InstallationError('설치 실패로 기존 파일 복원 시도: ' + str(error)) from error
    print(f'14차 설치 완료: {len(changes)}개 파일 수정/추가 · 백업 {backup}')
    print('태그 78개 연결 유지 · 프론트엔드/저장 스키마/API 반환 형식 변경 없음')


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--check', action='store_true')
    p.add_argument('--root', type=Path, default=Path.cwd())
    args = p.parse_args()
    try:
        if args.check:
            todo = preflight(args.root)
            print(f'14차 사전 검사 통과: {len(todo)}개 파일 수정/추가 예정')
            for item in todo:
                print(' -', item.path.relative_to(args.root.resolve()))
        else:
            install(args.root)
        return 0
    except (InstallationError, OSError, ValueError, UnicodeError, SyntaxError) as error:
        print('14차 설치 중단:', error, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
