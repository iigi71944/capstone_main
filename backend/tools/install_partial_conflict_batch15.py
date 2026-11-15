"""Install Batch 15 over verified GitHub main e9f4b6b (Batch 14).

Only style_apply_service.py is edited. Four new backend files are created.
Reads and checks every input before writing, retains UTF-8 BOM and CRLF,
backs up the changed original under .git/, and rolls back on failure.

From capstone_main root:
    python backend/tools/install_partial_conflict_batch15.py --check
    python backend/tools/install_partial_conflict_batch15.py
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

APPLY_SERVICE = 'backend/app/services/style_apply_service.py'
BASELINE_GIT_BLOB = 'fe3f25a3c8298af3bbe51391ca4a4ee91b248dab'
PAYLOAD_DIR = Path(__file__).resolve().parent / 'batch15_payload'
NEW = {
    'backend/app/services/style_partial_conflict_service.py':
        'style_partial_conflict_service.py.source',
    'backend/tests/test_style_partial_conflict_batch15.py':
        'test_style_partial_conflict_batch15.py.source',
    'backend/tests/test_style_partial_conflict_integration_batch15.py':
        'test_style_partial_conflict_integration_batch15.py.source',
    'backend/tools/audit_transform_partial_conflicts_batch15.py':
        'audit_transform_partial_conflicts_batch15.py.source',
}

# Filled with each source file's SHA256 by the packaging script.
PAYLOAD_SHA256 = {
    'style_partial_conflict_service.py.source': 'ee21f4f90d2b1f6b837afbee4445f774cf94296b45bf36e39581474393fca089',
    'test_style_partial_conflict_batch15.py.source': 'ce3d5b9f842657233752ae2d5e022eb457f159619ba5d38c70195b112bcec58d',
    'test_style_partial_conflict_integration_batch15.py.source': 'c54f70c840e4b1a30cee26440107ed620fe50e4708e9debad4a306456946998a',
    'audit_transform_partial_conflicts_batch15.py.source': '4029b602145f65506f6e32d6ca3863c3302859df4e08ded35b6b644760bd94b5',
}

OLD_IMPORT = '''# CAPSTONE_BATCH14_CONFLICT_IMPORT_V1
from app.services.style_action_conflict_service import mark_reverted_actions
'''
NEW_IMPORT = OLD_IMPORT + '''# CAPSTONE_BATCH15_PARTIAL_CONFLICT_IMPORT_V1
from app.services.style_partial_conflict_service import mark_partially_reverted_actions
'''
OLD_RECONCILE = '''    # CAPSTONE_BATCH14_CONFLICT_RECONCILE_V1: an action can undo earlier
    # actions even when a later action creates a nonempty final difference.
    # Only complete checkpoint reversions are detectable without re-execution.
    if mark_reverted_actions(action_snapshots, action_results, normalize=_normalize_code):
        applied_rules[:] = [
            note
            for index, notes in enumerate(action_rules_by_step)
            if action_results[index].get('status') == 'applied'
            for note in notes
        ]
'''
NEW_RECONCILE = '''    # CAPSTONE_BATCH14_CONFLICT_RECONCILE_V1: preserve whole-file reversions.
    full_cancellations = mark_reverted_actions(
        action_snapshots, action_results, normalize=_normalize_code
    )
    # CAPSTONE_BATCH15_PARTIAL_CONFLICT_LEDGER_V1: only stable, uniquely named
    # top-level code scopes can be reconciled independently. Unknown scopes
    # retain Batch 14's verdict and never trigger speculative cancellation.
    partial_cancellations = mark_partially_reverted_actions(
        action_snapshots, action_results
    )
    if full_cancellations or partial_cancellations:
        applied_rules[:] = [
            note
            for index, notes in enumerate(action_rules_by_step)
            if action_results[index].get('status') == 'applied'
            for note in notes
        ]
'''
MARKERS = ('CAPSTONE_BATCH15_PARTIAL_CONFLICT_IMPORT_V1',
           'CAPSTONE_BATCH15_PARTIAL_CONFLICT_LEDGER_V1')


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


def _patch(source: str) -> str:
    found = [marker in source for marker in MARKERS]
    if any(found):
        if (not all(found) or any(source.count(marker) != 1 for marker in MARKERS)
                or source.count(NEW_IMPORT) != 1
                or source.count(NEW_RECONCILE) != 1):
            raise InstallationError('15차가 부분 적용되었거나 기존 패치 영역이 변경되었습니다.')
        ast.parse(source)
        return source

    if source.count(OLD_IMPORT) != 1 or source.count(OLD_RECONCILE) != 1:
        raise InstallationError('14차 스타일 적용 코드의 기준 위치가 일치하지 않습니다.')
    updated = source.replace(OLD_IMPORT, NEW_IMPORT, 1)
    updated = updated.replace(OLD_RECONCILE, NEW_RECONCILE, 1)
    ast.parse(updated)
    return updated


def preflight(root: Path) -> list[Change]:
    root = root.resolve()
    if not (root / '.git').is_dir() or not (root / 'backend/app/services').is_dir():
        raise InstallationError('capstone_main 프로젝트 최상위 폴더에서 실행해 주세요.')
    target = root / APPLY_SERVICE
    if not target.is_file():
        raise InstallationError('스타일 적용 서비스 파일을 찾을 수 없습니다.')
    original = target.read_bytes()
    source, bom, crlf = _decode(original)
    installed = all(marker in source for marker in MARKERS)
    if not installed and _git_blob(original) != BASELINE_GIT_BLOB:
        raise InstallationError('14차 GitHub e9f4b6b와 코드가 달라 수정하지 않았습니다.')
    updated = _patch(source)
    changes: list[Change] = []
    if updated != source:
        changes.append(Change(target, original, _encode(updated, bom, crlf)))

    for rel, payload in NEW.items():
        path = PAYLOAD_DIR / payload
        destination = root / rel
        if not path.is_file():
            raise InstallationError('15차 ZIP 파일 누락: ' + payload)
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != PAYLOAD_SHA256[payload]:
            raise InstallationError('15차 배포 파일 체크섬 오류: ' + payload)
        ast.parse(content.decode('utf-8'), filename=payload)
        if destination.exists():
            if not destination.is_file() or _normalized(destination.read_bytes()) != _normalized(content):
                raise InstallationError('기존 동명 파일이 달라 덮어쓰지 않습니다: ' + rel)
        else:
            changes.append(Change(destination, None, content))

    if installed and changes:
        raise InstallationError('15차 일부 파일이 누락된 부분 설치 상태입니다.')
    if not installed and len(changes) != len(NEW) + 1:
        raise InstallationError('15차 구성 파일 일부가 이미 존재하여 설치하지 않았습니다.')
    return changes


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode='wb', dir=path.parent, prefix='.capstone15_', suffix='.tmp', delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def install(root: Path) -> None:
    root = root.resolve()
    changes = preflight(root)
    if not changes:
        print('15차가 이미 설치되어 있습니다. 변경 사항이 없습니다.')
        return
    backup = root / '.git' / 'capstone_batch15_backups' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup.mkdir(parents=True, exist_ok=False)
    for change in changes:
        if change.old is not None:
            archive = backup / change.path.relative_to(root)
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(change.old)
    written: list[Change] = []
    try:
        for change in changes:
            if change.old is None and change.path.exists():
                raise InstallationError('검사 이후 동명 파일이 생겼습니다: ' + str(change.path))
            if change.old is not None and change.path.read_bytes() != change.old:
                raise InstallationError('사전 검사 이후 기존 파일이 변경되었습니다: ' + str(change.path))
            _atomic_write(change.path, change.new)
            written.append(change)
        if preflight(root):
            raise InstallationError('설치 후 검증 실패: 변경할 파일이 남았습니다.')
    except Exception as error:
        for change in reversed(written):
            try:
                if change.old is None:
                    change.path.unlink(missing_ok=True)
                else:
                    _atomic_write(change.path, change.old)
            except OSError:
                pass
        raise InstallationError('15차 설치 오류, 복원을 시도했습니다: ' + str(error)) from error
    print(f'15차 설치 완료: {len(changes)}개 파일 수정·추가 / 백업: {backup}')
    print('태그 102개, 연결 78개, 스타일 저장 형식, API, 프론트엔드는 그대로 유지합니다.')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        if args.check:
            changes = preflight(args.root)
            print(f'15차 사전 검사 통과: {len(changes)}개 파일 수정·추가 예정')
            for change in changes:
                print(' -', change.path.relative_to(args.root.resolve()))
        else:
            install(args.root)
        return 0
    except (InstallationError, OSError, UnicodeError, ValueError, SyntaxError) as error:
        print('15차 설치 중단:', error, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
