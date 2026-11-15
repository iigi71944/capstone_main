"""Portable non-destructive installer for three-pattern coverage batch 6.

Does not edit existing project files, auto-transform code, style settings,
or frontend. Installation is atomic per file and rejects divergent versions.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PAYLOAD = Path(__file__).parent / 'three_pattern_batch6_payload'
FILES = {
    'test_style_three_pattern_expansion_batch6.py.source':
        BACKEND / 'tests' / 'test_style_three_pattern_expansion_batch6.py',
    'audit_transform_three_patterns_extended.py.source':
        BACKEND / 'tools' / 'audit_transform_three_patterns_extended.py',
}
REQUIRED = (
    BACKEND / 'tools' / 'audit_transform_three_patterns.py',
    BACKEND / 'tests' / 'test_remaining_transform_batch1.py',
    BACKEND / 'app' / 'services' / 'improvement' / 'safe_syntax_patterns_service.py',
    BACKEND / 'app' / 'services' / 'improvement' / 'safe_structural_patterns_service.py',
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='validate without writing')
    args = parser.parse_args()
    issues = []
    for required in REQUIRED:
        if not required.is_file():
            issues.append(f'필수 기존 파일이 없습니다: {required.relative_to(BACKEND)}')
    new = []
    already = []
    for source_name, target in FILES.items():
        source = PAYLOAD / source_name
        if not source.is_file():
            issues.append(f'패치 파일이 없습니다: {source}')
            continue
        data = source.read_bytes()
        if target.exists():
            if not target.is_file() or digest(target.read_bytes()) != digest(data):
                issues.append(f'기존 파일이 다른 버전입니다. 덮어쓰지 않습니다: {target.relative_to(BACKEND)}')
            else:
                already.append((source, target))
        else:
            new.append((source, target))
    if issues:
        print('검사 중단:')
        for issue in issues:
            print(' -', issue)
        return 1
    print(f'검사 통과: 신규 파일 {len(new)}개, 이미 설치됨 {len(already)}개')
    if args.check:
        return 0
    created = []
    try:
        for source, target in new:
            target.parent.mkdir(parents=True, exist_ok=True)
            # exclusive creation prevents overwriting concurrent edits
            with target.open('xb') as handle:
                handle.write(source.read_bytes())
            created.append(target)
            print('설치:', target.relative_to(BACKEND))
    except (OSError, ValueError) as error:
        print('설치 오류, 이번 실행에서 만든 파일을 복구합니다:', error)
        for target in created:
            target.unlink(missing_ok=True)
        return 1
    print('완료: 기존 백엔드 소스/프론트엔드 파일 변경 없음')
    return 0


if __name__ == '__main__':
    sys.exit(main())
