"""Safely install the line-break style upgrade without overwriting user files.

Only two already-installed formatting services are upgraded, and one dedicated
linebreak service plus its tests are added. Existing tag transforms, routes,
frontend and execution verifier are not changed. Strict preflight and backup.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
from pathlib import Path
import sys
import tempfile

MARK = 'CAPSTONE_LINEBREAK_STYLE_V1'
EXPECTED_OLD = {
    'backend/app/services/style_format_profile_service.py': 'fb6a917fa9e2a4768e12cfc95ab63c4ef23ab5999900433195805e8e4bb17333',
    'backend/app/services/style_format_apply_service.py': '50a226cc64bd441f0aa74a954eba455398c2344e0d4df24a1d62e7d8a4de4e2f',
}
TARGETS = {
    'backend/app/services/style_format_profile_service.py': 'style_format_profile_service.source',
    'backend/app/services/style_format_apply_service.py': 'style_format_apply_service.source',
    'backend/app/services/style_linebreak_service.py': 'style_linebreak_service.source',
    'backend/tests/test_style_linebreak_upgrade.py': 'test_style_linebreak_upgrade.source',
}


class InstallationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Change:
    path: Path
    old: bytes | None
    new: bytes


def _decode(raw: bytes, name: str) -> tuple[str, bool, bool]:
    bom = raw.startswith(b'\xef\xbb\xbf')
    raw = raw[3:] if bom else raw
    try:
        source = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise InstallationError(name + ': UTF-8 파일이 아닙니다. 변경하지 않습니다.') from exc
    return source.replace('\r\n', '\n'), bom, b'\r\n' in raw


def _hash(source: str) -> str:
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def plan(root: Path, payload: Path | None = None) -> list[Change]:
    root = Path(root)
    payload = Path(payload) if payload is not None else Path(__file__).resolve().parent / 'linebreak_payload'
    if not (root / 'backend/app/api/routes/style_apply.py').exists():
        raise InstallationError('프로젝트 루트를 찾지 못했습니다. capstone_main에서 설치해 주세요.')
    # Preserve existing routing/verification contract: this upgrade does not
    # install missing prerequisites or alter execution validation.
    route = (root / 'backend/app/api/routes/style_apply.py').read_bytes()
    route_source, _, _ = _decode(route, 'style_apply.py')
    if 'CAPSTONE_SAVED_FORMAT_APPLY_V1' not in route_source or 'CAPSTONE_FORMATTING_EXECUTION_VERIFY_V2' not in route_source:
        raise InstallationError('서식 적용·실행 결과 복구 기능이 먼저 설치되어 있어야 합니다.')
    source_data: dict[str, bytes] = {}
    new_codes: dict[str, str] = {}
    for relative, filename in TARGETS.items():
        path = payload / filename
        if not path.is_file():
            raise InstallationError('설치용 파일이 없습니다: ' + filename)
        raw = path.read_bytes()
        source, _, _ = _decode(raw, filename)
        try:
            ast.parse(source)
        except SyntaxError as exc:
            raise InstallationError('설치용 Python 소스 문법 오류: ' + filename) from exc
        if filename.startswith(('style_format_profile_', 'style_format_apply_')) and MARK not in source:
            raise InstallationError('서식 연결 표식이 없는 설치용 파일: ' + filename)
        source_data[relative] = raw
        new_codes[relative] = source
    changes: list[Change] = []
    already = 0
    for relative in TARGETS:
        path = root / relative
        expected = new_codes[relative]
        if path.exists():
            old = path.read_bytes()
            original, bom, crlf = _decode(old, relative)
            if original == expected:
                already += 1
                continue
            if relative not in EXPECTED_OLD or _hash(original) != EXPECTED_OLD[relative]:
                raise InstallationError(
                    relative + ': 기존 파일이 예상한 버전과 다릅니다. '
                    '코드를 덮어쓰지 않았습니다. 변경한 파일을 확인해 주세요.'
                )
            formatted = expected.replace('\n', '\r\n') if crlf else expected
            new = (b'\xef\xbb\xbf' if bom else b'') + formatted.encode('utf-8')
            changes.append(Change(path, old, new))
        else:
            if relative in EXPECTED_OLD:
                raise InstallationError('기존 서식 서비스를 찾지 못했습니다: ' + relative)
            changes.append(Change(path, None, expected.encode('utf-8')))
    if already and changes:
        # A fully updated first service and an unchanged second service is not
        # automatically recoverable: fail closed on partial installation.
        raise InstallationError('일부 파일만 새 버전입니다. 수동 확인 후 진행해 주세요.')
    return changes


def install(root: Path, backup_root: Path | None = None, payload: Path | None = None) -> list[str]:
    root = Path(root)
    changes = plan(root, payload)
    if not changes:
        return ['이미 줄바꿈 스타일 업데이트가 설치되어 있습니다.']
    if backup_root is None:
        git = root / '.git'
        backup_root = (git / 'capstone_linebreak_style_backup_20261114'
                       if git.is_dir() else Path(tempfile.mkdtemp(prefix='capstone_linebreak_backup_')))
    backup_root = Path(backup_root)
    for entry in changes:
        if entry.old is None:
            continue
        backup_path = backup_root / entry.path.relative_to(root)
        if backup_path.exists():
            raise InstallationError('기존 백업을 덮어쓰지 않습니다: ' + str(backup_path))
    for entry in changes:
        if entry.old is None:
            continue
        backup_path = backup_root / entry.path.relative_to(root)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_bytes(entry.old)
    changed: list[Change] = []
    try:
        for entry in changes:
            entry.path.parent.mkdir(parents=True, exist_ok=True)
            entry.path.write_bytes(entry.new)
            changed.append(entry)
    except BaseException:
        for entry in reversed(changed):
            if entry.old is None:
                entry.path.unlink(missing_ok=True)
            else:
                entry.path.write_bytes(entry.old)
        raise
    return [str(entry.path.relative_to(root)) for entry in changes] + ['백업: ' + str(backup_root)]


def main() -> int:
    args = sys.argv[1:]
    if args not in ([], ['--check']):
        print('사용법: python backend/tools/install_linebreak_style.py [--check]')
        return 2
    root = Path(__file__).resolve().parents[2]
    try:
        if args:
            changes = plan(root)
            print('[사전 검사 정상] 다음 파일만 수정 또는 추가합니다:')
            for entry in changes:
                print('  ' + str(entry.path.relative_to(root)))
            print('[사전 검사 완료] 실제 파일은 변경하지 않았습니다.' if changes else '[사전 검사 완료] 이미 설치되어 있습니다.')
        else:
            for item in install(root):
                print('[설치 완료] ' + item)
    except (InstallationError, OSError, UnicodeError) as exc:
        print('[설치 중단] ' + str(exc))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
