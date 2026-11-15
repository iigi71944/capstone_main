"""Install isolated long-code function/method transformation enhancement.

Preserves the user's existing service, formatter, and frontend. Adds one helper,
one regression test file, and makes two small, checked insertions in the saved
style service. Never blindly replaces a user's existing service source.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile

MARK = 'CAPSTONE_LARGE_CODE_SCOPES_V1'
ROOT_SERVICE = Path('backend/app/services/style_apply_service.py')
ADDED = (
    Path('backend/app/services/style_large_code_service.py'),
    Path('backend/tests/test_style_large_code_scope.py'),
)
ORIGINAL_ANCHOR = '''    if _normalize_code(code) == _normalize_code(transformed_code):
        transformed_code = code
'''
GUARD_ANCHOR = '''            or (strict_runtime_validation and verification_status != "equivalent")
'''

INSERT = '''    # CAPSTONE_LARGE_CODE_SCOPES_V1: independent local plans for long Python files.
    # Preserve the existing whole-program actions, formatting pipeline and API.
    scoped_changes = False
    try:
        from app.services.style_large_code_service import apply_scoped_style_to_large_code
        locally_transformed, scoped_applied, scoped_warnings = apply_scoped_style_to_large_code(
            code=transformed_code,
            style=style,
            compare_style=compare_style_with_target_code,
            build_plan=build_transform_plan,
            get_transformer=_get_transform_function,
        )
        for note in scoped_warnings:
            _add_unique(warnings, note)
        if scoped_applied and locally_transformed != transformed_code:
            transformed_code = locally_transformed
            scoped_changes = True
            for item in scoped_applied:
                action_results.append({
                    "tag": item.get("tag", ""),
                    "action": item.get("action", ""),
                    "status": "applied",
                })
                applied_rules.append(
                    "적용 완료: 긴 코드의 " + item.get("scope", "함수")
                    + " 범위에 " + item.get("action", "") + " 변환"
                )
    except Exception as error:
        _add_unique(
            warnings,
            "긴 코드의 함수·메서드별 추가 변환 중 오류(" + type(error).__name__
            + ")가 발생하여 해당 추가 단계를 생략했습니다.",
        )

'''


class InstallationError(RuntimeError):
    pass


@dataclass
class Change:
    path: Path
    old: bytes | None
    new: bytes


def _decode(raw: bytes, filename: str) -> tuple[str, bool, bool]:
    bom = raw.startswith(b'\xef\xbb\xbf')
    payload = raw[3:] if bom else raw
    try:
        return payload.decode('utf-8').replace('\r\n', '\n'), bom, b'\r\n' in payload
    except UnicodeDecodeError as exc:
        raise InstallationError(filename + ': UTF-8 형식이 아니어서 변경하지 않았습니다.') from exc


def patch_service(source: str) -> str:
    if MARK in source:
        if 'or ((strict_runtime_validation or scoped_changes)' not in source:
            raise InstallationError('긴 코드 변환 코드가 일부만 설치된 상태입니다.')
        return source
    if source.count(ORIGINAL_ANCHOR) != 1:
        raise InstallationError('기존 코드 적용 서비스의 변환 완료 위치를 확인하지 못했습니다.')
    if source.count(GUARD_ANCHOR) != 1:
        raise InstallationError('기존 실행 결과 검증 위치를 확인하지 못했습니다.')
    source = source.replace(ORIGINAL_ANCHOR, INSERT + ORIGINAL_ANCHOR, 1)
    source = source.replace(
        GUARD_ANCHOR,
        '''            or ((strict_runtime_validation or scoped_changes)
                and verification_status != "equivalent")
''', 1)
    ast.parse(source)
    return source


def plan(root: Path) -> list[Change]:
    root = Path(root)
    if not (root / ROOT_SERVICE).is_file():
        raise InstallationError('capstone_main 프로젝트 최상위 폴더에서 실행해 주세요.')
    source_raw = (root / ROOT_SERVICE).read_bytes()
    source, bom, crlf = _decode(source_raw, str(ROOT_SERVICE))
    patched = patch_service(source)
    planned: list[Change] = []
    if patched != source:
        payload = patched.replace('\n', '\r\n') if crlf else patched
        patched_raw = (b'\xef\xbb\xbf' if bom else b'') + payload.encode('utf-8')
        planned.append(Change(root / ROOT_SERVICE, source_raw, patched_raw))
    for relative in ADDED:
        bundled = Path(__file__).resolve().parent / 'large_code_payload' / (relative.name + '.source')
        if not bundled.is_file():
            raise InstallationError('압축이 잘못 풀렸습니다: ' + str(relative))
        new_content = bundled.read_bytes()
        new_source, _, _ = _decode(new_content, str(relative))
        ast.parse(new_source)
        target = root / relative
        if target.is_file():
            old = target.read_bytes()
            old_source, _, _ = _decode(old, str(relative))
            if old_source != new_source:
                raise InstallationError(str(relative) + ': 같은 경로에 다른 내용의 파일이 있습니다. 변경하지 않았습니다.')
        else:
            planned.append(Change(target, None, new_content))
    # Reject a partially installed source + unrecognized new helper file.
    if not planned and MARK not in source:
        raise InstallationError('설치 상태를 확인할 수 없습니다.')
    return planned


def install(root: Path, backup_root: Path | None = None) -> list[str]:
    root = Path(root)
    changes = plan(root)
    if not changes:
        return ['이미 긴 코드 함수·메서드별 추가 변환이 설치되어 있습니다.']
    if backup_root is None:
        git_dir = root / '.git'
        backup_root = (
            git_dir / 'capstone_large_code_scope_backup_20261115'
            if git_dir.is_dir()
            else Path(tempfile.mkdtemp(prefix='capstone_long_code_backup_'))
        )
    backup_root = Path(backup_root)
    for item in changes:
        if item.old is not None and (backup_root / item.path.relative_to(root)).exists():
            raise InstallationError('백업 파일이 이미 있습니다. 덮어쓰지 않습니다.')
    for item in changes:
        if item.old is not None:
            destination = backup_root / item.path.relative_to(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(item.old)
    committed: list[Change] = []
    try:
        for item in changes:
            item.path.parent.mkdir(parents=True, exist_ok=True)
            item.path.write_bytes(item.new)
            committed.append(item)
    except BaseException:
        for item in reversed(committed):
            if item.old is None:
                item.path.unlink(missing_ok=True)
            else:
                item.path.write_bytes(item.old)
        raise
    return [str(item.path.relative_to(root)) for item in changes] + ['백업: ' + str(backup_root)]


def main() -> int:
    args = sys.argv[1:]
    if args not in ([], ['--check']):
        print('사용법: python backend/tools/install_large_code_scope.py [--check]')
        return 2
    root = Path(__file__).resolve().parents[2]
    try:
        if args:
            changes = plan(root)
            print('[사전 검사 정상] 수정·추가 예정 파일:')
            for item in changes:
                print('  ' + str(item.path.relative_to(root)))
            print('[사전 검사 완료] 프로젝트 파일은 변경하지 않았습니다.')
        else:
            for line in install(root):
                print('[설치 완료] ' + line)
    except (InstallationError, OSError, SyntaxError, UnicodeError) as exc:
        print('[설치 중단] ' + str(exc))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
