"""Install saved-formatting application into the actual Git-based backend routes.

Only these two existing files are changed, after a full preflight:
  backend/app/schemas/style_apply.py
  backend/app/api/routes/style_apply.py
The original frontend and tag transformations are not touched.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re
import sys
import tempfile

MARK = "CAPSTONE_SAVED_FORMAT_APPLY_V1"


class InstallationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Change:
    path: Path
    previous: bytes
    replacement: bytes


def _one(source: str, search: str, filename: str) -> None:
    count = source.count(search)
    if count != 1:
        raise InstallationError(f"{filename}: 예상한 연결 위치가 {count}회 발견되었습니다. 기존 파일은 변경하지 않습니다.")


def patch_schema(source: str) -> str:
    if MARK in source:
        return source
    try:
        parsed = ast.parse(source)
    except SyntaxError as exc:
        raise InstallationError("style_apply.py 스키마 구문이 유효하지 않습니다.") from exc
    matches = [node for node in parsed.body if isinstance(node, ast.ClassDef) and node.name == "CodingStylePayload"]
    if len(matches) != 1:
        raise InstallationError("CodingStylePayload를 정확히 한 개 찾지 못했습니다.")
    klass = matches[0]
    if any(isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == 'formatting_style' for n in klass.body):
        raise InstallationError("CodingStylePayload에 기존 formatting_style 필드가 있습니다. 중복 수정을 중단합니다.")
    lines = source.splitlines(keepends=True)
    section = ''.join(lines[klass.lineno - 1:klass.end_lineno])
    _one(section, '    created_at: str\n', 'CodingStylePayload')
    updated = section.replace('    created_at: str\n',
        '    created_at: str\n\n'
        f'    # {MARK}: 기존 스타일 JSON의 서식 프로필을 보존\n'
        '    formatting_style: Optional[Dict[str, Any]] = None\n', 1)
    new = ''.join(lines[:klass.lineno - 1]) + updated + ''.join(lines[klass.end_lineno:])
    ast.parse(new)
    return new


def patch_route(source: str) -> str:
    if MARK in source:
        return source
    try:
        parsed = ast.parse(source)
    except SyntaxError as exc:
        raise InstallationError("style_apply.py 라우트 구문이 유효하지 않습니다.") from exc
    if len([node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == 'apply_style_api']) != 1:
        raise InstallationError('apply_style_api 함수가 하나인지 확인할 수 없습니다.')
    import_anchor = 'from app.services.style_apply_service import apply_coding_style\n'
    return_anchor = '        return StyleApplyResponse(\n            success=True,'
    _one(source, import_anchor, 'style_apply 라우트 import')
    _one(source, return_anchor, 'style_apply 라우트 성공 응답')
    source = source.replace(import_anchor,
        import_anchor + 'from app.services.style_format_apply_service import apply_saved_formatting_style\n', 1)
    bridge = f'''        # {MARK}: 기존 문법/개념 변환과 실행 검증이 끝난 뒤 서식을 적용합니다.
        # 프로필이 없는 기존 저장 스타일은 기존 동작과 완전히 같습니다.
        formatting_profile = request.style.formatting_style
        verification_status = (
            execution_verification.get("status")
            if isinstance(execution_verification, dict)
            else None
        )
        prior_transform_rolled_back = (
            transformed_code == request.code
            and any(
                "전체 변환을 취소" in str(note)
                for note in warnings
            )
        )
        if formatting_profile is not None and not (
            verification_status == "different" or prior_transform_rolled_back
        ):
            formatted_code, format_rules, format_warnings = apply_saved_formatting_style(
                transformed_code, formatting_profile
            )
            if formatted_code != transformed_code:
                transformed_code = formatted_code
                applied_rules.extend(format_rules)
                if execution_verification is None:
                    summary = (summary or "").replace(
                        "최종 코드 변경이 없어 별도의 실행 결과 비교를 수행하지 않았습니다.",
                        "문법/개념 태그 변환으로 인한 구조 변경이 없어 별도의 실행 결과 비교를 수행하지 않았습니다.",
                    )
                summary = (summary or "") + (
                    " 저장된 서식을 최종 코드에 적용했습니다. "
                    "서식은 Python AST 구조 동일성을 확인했으며, "
                    "줄 번호 관찰 등 모든 동작의 동등성을 보증하지 않습니다."
                )
            warnings.extend(format_warnings)
        elif formatting_profile is not None:
            warnings.append(
                "기존 문법/개념 변환이 검증 과정에서 취소되어 서식 적용도 생략했습니다."
            )

'''
    source = source.replace(return_anchor, bridge + return_anchor, 1)
    ast.parse(source)
    return source


def _decode(raw: bytes) -> tuple[str, bool, bool]:
    bom = raw.startswith(b'\xef\xbb\xbf')
    txt = raw[3:] if bom else raw
    try:
        content = txt.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise InstallationError(
            '기존 소스 파일이 UTF-8 인코딩이 아닙니다. 원본을 변경하지 않고 설치를 중단합니다.'
        ) from exc
    crlf = '\r\n' in content and content.count('\r\n') >= content.count('\n') / 2
    return content.replace('\r\n', '\n'), bom, crlf


def plan(root: Path) -> list[Change]:
    root = Path(root)
    required = [
        root / 'backend/app/services/style_format_profile_service.py',
        root / 'backend/app/services/style_apply_service.py',
        root / 'frontend/lib/codingStyleFactory.ts',
        root / 'frontend/types/analysis.ts',
    ]
    for req in required:
        if not req.is_file():
            raise InstallationError('선행 서식 추출 기능이 확인되지 않았습니다: ' + str(req.relative_to(root)))
    if 'formatting_style' not in (root / 'frontend/lib/codingStyleFactory.ts').read_text(encoding='utf-8-sig'):
        raise InstallationError('선행 서식 저장 기능 연결이 없습니다. 먼저 이전 Git 대응 ZIP 설치를 완료해야 합니다.')
    specs = [
        ('backend/app/schemas/style_apply.py', patch_schema),
        ('backend/app/api/routes/style_apply.py', patch_route),
    ]
    changes = []
    marked = []
    for rel, patcher in specs:
        path = root / rel
        if not path.is_file():
            raise InstallationError('변경 대상 파일을 찾지 못했습니다: ' + rel)
        original = path.read_bytes()
        source, bom, crlf = _decode(original)
        marked.append(MARK in source)
        updated = patcher(source)
        if updated != source:
            if crlf:
                updated = updated.replace('\n', '\r\n')
            output = (b'\xef\xbb\xbf' if bom else b'') + updated.encode('utf-8')
            changes.append(Change(path, original, output))
    if any(marked) and not all(marked):
        raise InstallationError('서식 적용 기능이 일부 파일에만 설치되어 중복 수정 위험이 있습니다. 자동 설치를 중단합니다.')
    return changes


def install(root: Path, backup_root: Path | None = None) -> list[str]:
    root = Path(root)
    changes = plan(root)
    if not changes:
        return ['이미 설치되어 있습니다. 변경한 파일이 없습니다.']
    if backup_root is None:
        git = root / '.git'
        backup_root = (git / 'capstone_saved_format_apply_backup') if git.is_dir() else Path(tempfile.mkdtemp(prefix='capstone_saved_format_apply_backup_'))
    backup_root = Path(backup_root)
    for item in changes:
        target = backup_root / item.path.relative_to(root)
        if target.exists():
            raise InstallationError('기존 백업을 덮어쓰지 않습니다: ' + str(target))
    for item in changes:
        target = backup_root / item.path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.previous)
    modified = []
    try:
        for item in changes:
            item.path.write_bytes(item.replacement)
            modified.append(item)
    except BaseException:
        for item in reversed(modified):
            item.path.write_bytes(item.previous)
        raise
    return [str(item.path.relative_to(root)) for item in changes] + ['backup: ' + str(backup_root)]


def main() -> int:
    args = sys.argv[1:]
    if args not in ([], ['--check']):
        print('사용법: python backend/tools/install_formatting_apply.py [--check]')
        return 2
    root = Path(__file__).resolve().parents[2]
    try:
        if args:
            changes = plan(root)
            for item in changes:
                print('[사전 검사 정상] ' + str(item.path.relative_to(root)))
            print('[사전 검사 완료] 실제 파일은 변경하지 않았습니다.' if changes else '[사전 검사 완료] 이미 설치되어 있습니다.')
        else:
            for message in install(root):
                print('[완료] ' + message)
    except (InstallationError, OSError, UnicodeError) as error:
        print('[설치 중단] ' + str(error))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
