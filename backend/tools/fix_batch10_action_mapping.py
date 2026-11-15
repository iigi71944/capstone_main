"""Conservative repair for three Batch-10 tag/action name mismatches.

Use at capstone_main root:
  python backend/tools/fix_batch10_action_mapping.py --check
  python backend/tools/fix_batch10_action_mapping.py

Works with LF/CRLF and optional UTF-8 BOM. Modifies ONLY the registry file.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime
from hashlib import sha256
import os
from pathlib import Path
import re
import sys
import tempfile

REGISTRY = Path('backend/app/services/style_tag_transform_map_service.py')
DISPATCH = Path('backend/app/services/style_apply_service.py')
# Current actions are taken from the user's actual failing test output.
REPAIRS = {
    '복합 할당': ('create_safe_augmented_assignment', 'create_safe_augassign'),
    '검증 로직 중심 구조': ('create_safe_validation_condition', 'create_safe_validation_helper'),
    '반환 중심 구조': ('create_safe_multiple_returns', 'create_return_structure'),
}


class RepairError(Exception):
    pass


def decode_registry(data: bytes) -> tuple[str, bool, bool]:
    bom = data.startswith(b'\xef\xbb\xbf')
    data = data[3:] if bom else data
    crlf = b'\r\n' in data
    return data.decode('utf-8').replace('\r\n', '\n'), bom, crlf


def encode_registry(code: str, bom: bool, crlf: bool) -> bytes:
    return (b'\xef\xbb\xbf' if bom else b'') + code.replace('\n', '\r\n' if crlf else '\n').encode('utf-8')


def get_registry_entries(code: str) -> dict[str, str]:
    tree = ast.parse(code, filename=str(REGISTRY))
    assignments = []
    for node in tree.body:
        if (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
                and node.target.id == 'CREATE_ACTION_BY_TAG'):
            assignments.append(node.value)
        elif (isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == 'CREATE_ACTION_BY_TAG'
                      for target in node.targets)):
            assignments.append(node.value)
    if len(assignments) != 1 or not isinstance(assignments[0], ast.Dict):
        raise RepairError('CREATE_ACTION_BY_TAG 딕셔너리를 고유하게 찾지 못했습니다.')
    values = {}
    for key, val in zip(assignments[0].keys, assignments[0].values):
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                if key.value in values:
                    raise RepairError('중복 태그 감지: ' + key.value)
                values[key.value] = val.value
    return values


def patch_registry(code: str) -> tuple[str, list[tuple[str, str, str]]]:
    entries = get_registry_entries(code)
    modifications = []
    for tag, (old, new) in REPAIRS.items():
        current = entries.get(tag)
        if current == new:
            continue
        if current != old:
            raise RepairError(f"'{tag}' 예상하지 못한 액션: {current!r}. 덮어쓰지 않습니다.")
        line = re.compile(
            r'(?P<prefix>^[ \t]*[\"\']' + re.escape(tag) + r'[\"\'][ \t]*:[ \t]*[\"\'])'
            + re.escape(old)
            + r'(?P<suffix>[\"\'][ \t]*,?(?:[ \t]*\#[^\n]*)?$)',
            re.MULTILINE,
        )
        code, count = line.subn(lambda m: m.group('prefix') + new + m.group('suffix'), code)
        if count != 1:
            raise RepairError(f"'{tag}' 매핑을 정확히 한 번 찾아 수정하지 못했습니다. 파일 변경 없음.")
        modifications.append((tag, old, new))
    after = get_registry_entries(code)
    if any(after.get(tag) != new for tag, (_, new) in REPAIRS.items()):
        raise RepairError('수정 후 매핑 검증에 실패했습니다.')
    return code, modifications


def _atomic_write(path: Path, data: bytes) -> None:
    with tempfile.NamedTemporaryFile('wb', dir=path.parent, prefix='.capstone_b10map_', suffix='.tmp', delete=False) as fp:
        temp = Path(fp.name)
        fp.write(data)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def run(root: Path, check_only: bool) -> int:
    root = root.resolve()
    if not (root / '.git').is_dir() or not (root / 'backend/app/services').is_dir():
        raise RepairError('capstone_main 프로젝트 최상위 폴더에서 실행해야 합니다.')
    registry_path = root / REGISTRY
    dispatcher_path = root / DISPATCH
    if not registry_path.is_file() or not dispatcher_path.is_file():
        raise RepairError('레지스트리 또는 변환 실행기 파일이 없습니다.')
    # Check that the intended actions already exist; never insert a dead mapping.
    dispatcher_code = dispatcher_path.read_text(encoding='utf-8-sig')
    for _, (_, new) in REPAIRS.items():
        if not re.search(r'[\"\']' + re.escape(new) + r'[\"\']', dispatcher_code):
            raise RepairError('변환 실행기에 다음 액션이 없습니다: ' + new)
    original = registry_path.read_bytes()
    code, bom, crlf = decode_registry(original)
    updated, changes = patch_registry(code)
    if not changes:
        print('이미 3개 태그의 액션 연결이 정상입니다. 변경할 파일이 없습니다.')
        return 0
    for tag, old, new in changes:
        print(f'  {tag}: {old} -> {new}')
    print(f'검사 통과: 매핑 {len(changes)}개 수정 예정, 다른 파일 변경 없음')
    if check_only:
        return 0
    if registry_path.read_bytes() != original:
        raise RepairError('검사 중 레지스트리가 변경됐습니다. 설치 중단')
    backup_dir = root / '.git' / 'capstone_batch10_mapping_fix_backups' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup = backup_dir / REGISTRY.name
    backup.write_bytes(original)
    try:
        if registry_path.read_bytes() != original:
            raise RepairError('백업 후 파일이 변경됐습니다. 설치 중단')
        _atomic_write(registry_path, encode_registry(updated, bom, crlf))
        if get_registry_entries(decode_registry(registry_path.read_bytes())[0]) != get_registry_entries(updated):
            raise RepairError('수정 후 파일 검증 실패')
    except (OSError, RepairError, SyntaxError) as error:
        _atomic_write(registry_path, original)
        raise RepairError('오류 발생, 원본 복원: ' + str(error)) from error
    print('10차 매핑 수정 완료. 원본 백업:', backup)
    print('프론트엔드, 스타일 저장 방식, 변환기, 테스트 파일은 변경하지 않았습니다.')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='사전 검증만 수행')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        return run(args.root, args.check)
    except (RepairError, OSError, UnicodeError, SyntaxError) as error:
        print('수정 중단:', error, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
