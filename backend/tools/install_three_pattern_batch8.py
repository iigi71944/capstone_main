"""Safe cumulative batch-8 installer for Windows/Linux/macOS.

Only adds two test/audit files and changes one known LibCST transformer
anchor. Verifies batch-7 assets and a pinned upstream hash; never overwrites
unknown source changes. No frontend/style storage/comment-removal edits.
"""
from __future__ import annotations

import argparse
import ast
from hashlib import sha256
import os
from pathlib import Path
import sys
import tempfile

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
PAYLOAD = Path(__file__).resolve().parent / 'three_pattern_batch8_payload'
PREVIOUS = {
    'tools/audit_transform_three_patterns_batch7.py': '7921a22737d6a0640f6873e51b395447773438ea380ef39bf7f155567d7295aa',
    'tests/test_style_three_pattern_expansion_batch7.py': '29aab5cf493902595f16948f38562481412977f0bcbca90fd96854a5afac8b25',
}
NEW = {
    'audit_transform_three_patterns_batch8.py.source': 'tools/audit_transform_three_patterns_batch8.py',
    'test_style_three_pattern_expansion_batch8.py.source': 'tests/test_style_three_pattern_expansion_batch8.py',
}
EXPECTED_PAYLOAD = {
    'audit_transform_three_patterns_batch8.py.source': 'b27b79c6bbb715feb85cf6b7ef17e0543687e322750b291f983920ac543e9a1a',
    'test_style_three_pattern_expansion_batch8.py.source': '246690dac75a84b7e33e7edeb5dfac50f6b506594a8a6072b94c81f75c5b0f18',
}
FUNCTION = BACKEND / 'app/services/improvement/function_style_service.py'
BASE_DIGEST = '0ac870ac275089fa4f7df7a4c7b0da7a3f6f0b9b918dd9a75f63da1ff0600495'
PATCHED_DIGEST = 'eaf1be62de0d6c33c13aaf303dc7becf39cce15d4f7e6a5d0323bb2c86dc6f65'

OLD = '''        return updated_node.with_changes(\n            body=[\n                *preserved_body,\n                cst.EmptyLine(),\n                main_function,\n                cst.EmptyLine(),\n                main_guard,\n            ]\n        )'''
REPLACEMENT = '''        # EmptyLine nodes belong to the leading_lines of a statement, not\n        # directly in Module.body (which accepts BaseStatement nodes only).\n        main_function = main_function.with_changes(\n            leading_lines=[cst.EmptyLine()]\n        )\n        main_guard = main_guard.with_changes(\n            leading_lines=[cst.EmptyLine()]\n        )\n        return updated_node.with_changes(\n            body=[\n                *preserved_body,\n                main_function,\n                main_guard,\n            ]\n        )'''


def normalized(data: bytes) -> bytes:
    return data.removeprefix(b'\xef\xbb\xbf').replace(b'\r\n', b'\n')


def digest(data: bytes) -> str:
    return sha256(normalized(data)).hexdigest()


def build_change(raw: bytes) -> bytes:
    if digest(raw) != BASE_DIGEST:
        raise ValueError('기준 소스와 일치하지 않으므로 변환기를 수정할 수 없습니다')
    content = normalized(raw).decode('utf-8')
    if content.count(OLD) != 1:
        raise ValueError('LibCST 변환기 수정 위치가 일치하지 않습니다')
    updated = content.replace(OLD, REPLACEMENT)
    ast.parse(updated, filename=str(FUNCTION))
    if digest(updated.encode('utf-8')) != PATCHED_DIGEST:
        raise ValueError('LibCST 변환기 예상 변경 파일의 해시가 일치하지 않습니다')
    if b'\r\n' in raw:
        updated = updated.replace('\n', '\r\n')
    content_bytes = updated.encode('utf-8')
    if raw.startswith(b'\xef\xbb\xbf'):
        content_bytes = b'\xef\xbb\xbf' + content_bytes
    return content_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description='8차 3종 패턴 증거/LibCST 수정 안전 설치')
    parser.add_argument('--check', action='store_true', help='설치하지 않고 사전 검사')
    args = parser.parse_args()
    errors: list[str] = []

    # Verify previous successful batch. No archive action is permitted to
    # create or silently rewrite these existing paths.
    for relative, expected in PREVIOUS.items():
        target = BACKEND / relative
        if not target.is_file():
            errors.append(f'7차 패치 파일 없음: {relative}')
        elif digest(target.read_bytes()) != expected:
            errors.append(f'7차 패치 파일의 내용이 다름: {relative}')

    additions: list[tuple[Path, Path]] = []
    installed_count = 0
    for source_name, relative in NEW.items():
        source, target = PAYLOAD / source_name, BACKEND / relative
        if not source.is_file():
            errors.append(f'ZIP 내부 파일 없음: {source_name}')
            continue
        data = source.read_bytes()
        if digest(data) != EXPECTED_PAYLOAD[source_name]:
            errors.append(f'ZIP 내부 파일 해시 오류: {source_name}')
            continue
        try:
            ast.parse(data.decode('utf-8'), filename=source_name)
        except (SyntaxError, UnicodeError) as exc:
            errors.append(f'ZIP 내부 Python 문법 오류: {source_name}: {exc}')
            continue
        if target.exists():
            if not target.is_file() or digest(target.read_bytes()) != digest(data):
                errors.append(f'동일 경로에 다른 파일 존재, 덮어쓰지 않음: {relative}')
            else:
                installed_count += 1
        else:
            additions.append((source, target))

    current_data: bytes | None = None
    next_data: bytes | None = None
    if not FUNCTION.is_file():
        errors.append('변환기 없음: app/services/improvement/function_style_service.py')
    else:
        current_data = FUNCTION.read_bytes()
        function_digest = digest(current_data)
        if function_digest == BASE_DIGEST:
            try:
                next_data = build_change(current_data)
            except (SyntaxError, UnicodeError, ValueError) as exc:
                errors.append(f'변환기 패치 생성 실패: {exc}')
        elif function_digest == PATCHED_DIGEST:
            installed_count += 1
        else:
            errors.append('함수 구조 변환기 버전이 다릅니다. 다른 변경을 덮어쓰지 않습니다. SHA256=' + function_digest)

    if errors:
        print('설치 중단: 기존 파일을 수정하지 않았습니다.')
        for error in errors:
            print(' -', error)
        return 1
    print(f'설치 전 검사 통과: 신규 파일 {len(additions)}개, 이미 설치된 항목 {installed_count}개, 함수 변환기 수정 {int(next_data is not None)}개')
    if args.check:
        return 0

    created: list[Path] = []
    edited = False
    temporary_path: Path | None = None
    try:
        # Ensure rollback data is held in memory and in a .git backup, but do
        # not create new files until every preflight hash has passed.
        if next_data is not None and current_data is not None:
            backup_dir = REPO / '.git' / 'capstone_batch8_backups'
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / ('function_style_service_' + BASE_DIGEST[:12] + '.py')
            if backup.exists():
                if backup.read_bytes() != current_data:
                    raise OSError('기존 백업 파일의 내용이 달라 중단합니다')
            else:
                with backup.open('xb') as fp:
                    fp.write(current_data)
            print('원본 백업:', backup)

        for source, target in additions:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as fp:
                fp.write(source.read_bytes())
            created.append(target)
            print('신규 설치:', target.relative_to(BACKEND))

        if next_data is not None:
            assert current_data is not None
            if FUNCTION.read_bytes() != current_data:
                raise OSError('검사 후 변환기 파일이 변경되었습니다')
            with tempfile.NamedTemporaryFile(mode='wb', prefix='.capstone-batch8-',
                                             suffix='.py', dir=FUNCTION.parent,
                                             delete=False) as fp:
                temporary_path = Path(fp.name)
                fp.write(next_data)
            os.replace(temporary_path, FUNCTION)
            temporary_path = None
            edited = True
            print('변환기 수정:', FUNCTION.relative_to(BACKEND))
    except (OSError, ValueError) as exc:
        print('설치 실패, 생성된 파일을 복구합니다:', type(exc).__name__, str(exc))
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        if edited and current_data is not None:
            FUNCTION.write_bytes(current_data)
        for target in reversed(created):
            target.unlink(missing_ok=True)
        return 1

    print('완료: 스타일 저장/주석 제거/프론트엔드 파일 변경 없음')
    return 0


if __name__ == '__main__':
    sys.exit(main())
