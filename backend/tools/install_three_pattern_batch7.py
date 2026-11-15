"""Install the additive batch-7 evidence suite, safely on Windows/macOS.

This installer does not edit any existing source file, style storage, UI or
previous test. It verifies the prior batch-6 files, protects against filename
collisions, and creates the two new files exclusively.
"""
from __future__ import annotations

import argparse
import ast
from hashlib import sha256
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
PAYLOAD = Path(__file__).resolve().parent / 'three_pattern_batch7_payload'
PREVIOUS = {
    'tools/audit_transform_three_patterns_extended.py':
        '718a442b5d5611e4ae594aa69f58446550ddd5a5e4b454f6b94cc57cee8561cf',
    'tests/test_style_three_pattern_expansion_batch6.py':
        'eaf050aa4dfbc3af1e7cd66e4c4a4e736efa410d584c61b2656823bff9833a2f',
}
FILES = {
    'audit_transform_three_patterns_batch7.py.source':
        'tools/audit_transform_three_patterns_batch7.py',
    'test_style_three_pattern_expansion_batch7.py.source':
        'tests/test_style_three_pattern_expansion_batch7.py',
}
EXPECTED = {
    'audit_transform_three_patterns_batch7.py.source':
        '7921a22737d6a0640f6873e51b395447773438ea380ef39bf7f155567d7295aa',
    'test_style_three_pattern_expansion_batch7.py.source':
        '29aab5cf493902595f16948f38562481412977f0bcbca90fd96854a5afac8b25',
}
REQUIRED = (
    'tools/audit_transform_three_patterns.py',
    'tests/test_remaining_transform_batch4.py',
    'tests/test_safe_index_iteration_upgrade.py',
    'app/services/improvement/aggregation_style_service.py',
    'app/services/improvement/collection_style_service.py',
    'app/services/improvement/conditional_return_service.py',
    'app/services/improvement/mapping_style_service.py',
    'app/services/improvement/resource_style_service.py',
)


def digest(data: bytes, normalize: bool = False) -> str:
    if normalize:
        data = data.removeprefix(b'\xef\xbb\xbf').replace(b'\r\n', b'\n')
    return sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description='7차 자동 변환 3종 패턴 검사 파일 설치')
    parser.add_argument('--check', action='store_true', help='설치하지 않고 사전 검사만 수행')
    args = parser.parse_args()
    errors: list[str] = []

    for relative in REQUIRED:
        if not (BACKEND / relative).is_file():
            errors.append(f'기존 프로젝트 파일 없음: {relative}')
    for relative, expected in PREVIOUS.items():
        target = BACKEND / relative
        if not target.is_file():
            errors.append(f'6차 필수 파일 없음: {relative}')
        elif digest(target.read_bytes(), normalize=True) != expected:
            errors.append(f'6차 파일 내용 변경 감지(덮어쓰지 않음): {relative}')

    new_files: list[tuple[Path, Path]] = []
    already: list[Path] = []
    for source_name, relative in FILES.items():
        source = PAYLOAD / source_name
        target = BACKEND / relative
        if not source.is_file():
            errors.append(f'ZIP 내부 필수 파일 없음: {source_name}')
            continue
        data = source.read_bytes()
        if digest(data) != EXPECTED[source_name]:
            errors.append(f'ZIP 내부 파일 검증 실패: {source_name}')
            continue
        try:
            ast.parse(data.decode('utf-8'), filename=source_name)
        except (UnicodeError, SyntaxError) as exc:
            errors.append(f'Python 문법 검사 실패: {source_name} ({exc})')
            continue
        if target.exists():
            if not target.is_file() or digest(target.read_bytes(), normalize=True) != digest(data):
                errors.append(f'설치 대상에 다른 파일이 존재함(덮어쓰지 않음): {relative}')
            else:
                already.append(target)
        else:
            new_files.append((source, target))

    if errors:
        print('설치 중단: 기존 파일은 수정하지 않았습니다.')
        for error in errors:
            print(' -', error)
        return 1
    print(f'검사 통과: 신규 {len(new_files)}개, 이미 설치됨 {len(already)}개, 기존 파일 변경 없음')
    if args.check:
        return 0

    created: list[Path] = []
    try:
        for source, target in new_files:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as handle:  # Prevent overwrite on races.
                handle.write(source.read_bytes())
            created.append(target)
            print('설치:', target.relative_to(BACKEND))
    except (OSError, ValueError) as exc:
        print('설치 오류, 이번 실행에서 생성한 파일은 취소합니다:', exc)
        for target in reversed(created):
            target.unlink(missing_ok=True)
        return 1
    print('완료: 코드 변환기, 스타일 저장 방식, 주석 제거, 프론트엔드 변경 없음')
    return 0


if __name__ == '__main__':
    sys.exit(main())
