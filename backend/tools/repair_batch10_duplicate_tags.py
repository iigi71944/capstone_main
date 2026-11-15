"""Correct Batch 10 tag duplicates without altering earlier action mappings.

This is a scoped, fail-closed repair. Original files backed up in .git.
Run from capstone_main root; supports Windows CRLF and Mac/Linux LF.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import os
from pathlib import Path
import sys
import tempfile

B10_INSTALLER_SHA = '79839792ba187ce2ee693cd26be30dee95ebf4c586e07a28f61f30198c3626b3'
OLD_TEST_SHA = '2880a2f4df38422d6646a6603d93129e29b7ef177058b7cd76ec257d08cda8c2'
OLD_AUDIT_SHA = '059688f76506eec955c77195d8e35eddaee9695512f66cbe9a443de4923261bc'
NEW_TEST_SHA = '75aaaaf159ee3998b786118d8884ba6c195cb864403cad2836c2cc9afa453f67'
NEW_AUDIT_SHA = 'a7ae3b1ebe0e30c20175f8ebbda0f8dedd4a903b8028fc69501d839991ff45e0'

REGISTRY = Path('backend/app/services/style_tag_transform_map_service.py')
PLAN = Path('backend/app/services/style_transform_plan_service.py')
DISPATCH = Path('backend/app/services/style_apply_service.py')
TEST = Path('backend/tests/test_style_unmapped_patterns_batch10_integration.py')
AUDIT = Path('backend/tools/audit_transform_three_patterns_batch10.py')
ORIGINAL_INSTALLER = Path('backend/tools/install_unmapped_batch10.py')
PAYLOAD_DIR = Path(__file__).resolve().parent / 'batch10_duplicate_fix_payload'

EXISTING = {
    '복합 할당': 'create_safe_augmented_assignment',
    '키워드 인자 사용': 'create_safe_keyword_call',
    '검증 로직 중심 구조': 'create_safe_validation_condition',
    '반환 중심 구조': 'create_safe_multiple_returns',
}
NEW_TAG = {'enumerate 사용': 'create_safe_enumerate'}


class RepairError(Exception):
    pass


@dataclass(frozen=True)
class Change:
    path: Path
    original: bytes
    updated: bytes


def _digest_lf(raw: bytes) -> str:
    return sha256(raw.removeprefix(b'\xef\xbb\xbf').replace(b'\r\n', b'\n')).hexdigest()


def _decode(raw: bytes) -> tuple[str, bool, bool]:
    bom = raw.startswith(b'\xef\xbb\xbf')
    body = raw[3:] if bom else raw
    return body.decode('utf-8').replace('\r\n', '\n'), bom, b'\r\n' in body


def _encode(text: str, bom: bool, crlf: bool) -> bytes:
    if crlf:
        text = text.replace('\n', '\r\n')
    return (b'\xef\xbb\xbf' if bom else b'') + text.encode('utf-8')


def _get_old_block(installer: str, constant: str) -> str:
    tree = ast.parse(installer)
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == constant):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    raise RepairError('10차 설치기에서 블록을 찾지 못했습니다: ' + constant)


def _registry_pairs(text: str) -> list[tuple[str, str]]:
    tree = ast.parse(text)
    entries = [node.value for node in tree.body
               if isinstance(node, ast.AnnAssign)
               and isinstance(node.target, ast.Name)
               and node.target.id == 'CREATE_ACTION_BY_TAG']
    if len(entries) != 1 or not isinstance(entries[0], ast.Dict):
        raise RepairError('태그 등록 딕셔너리를 고유하게 찾을 수 없습니다.')
    result = []
    for key, value in zip(entries[0].keys, entries[0].values):
        if (not isinstance(key, ast.Constant) or not isinstance(key.value, str)
                or not isinstance(value, ast.Constant) or not isinstance(value.value, str)):
            raise RepairError('레지스트리에 동적 태그 또는 액션 값이 있습니다. 중단합니다.')
        result.append((key.value, value.value))
    return result


def _patch_block(text: str, old: str, new: str, label: str) -> str:
    if text.count(new) == 1 and text.count(old) == 0:
        return text
    if text.count(old) != 1 or text.count(new) != 0:
        raise RepairError(f'{label}: 예상한 10차 블록을 정확히 찾지 못했습니다.')
    return text.replace(old, new, 1)


def _expected_blocks(installer: str) -> tuple[str, str, str, str]:
    old_registry = _get_old_block(installer, 'REGISTRY_INSERT')
    old_plan = _get_old_block(installer, 'PLAN_INSERT')
    new_registry = old_registry.replace(
        'five newly linked syntax/concept tags.',
        'one newly linked syntax tag; 4 earlier links preserved.'
    )
    for tag, action in EXISTING.items():
        line = f'    "{tag}": "{action}",\n'
        # Existing keys must NOT be inserted by 10th batch, regardless of the
        # 10th batch's accidental action names for those keys.
        matches = [row for row in new_registry.splitlines(keepends=True)
                   if row.lstrip().startswith(f'"{tag}":')]
        if len(matches) != 1:
            raise RepairError('10차 중복 태그 원본 블록 예상 불일치: ' + tag)
        new_registry = new_registry.replace(matches[0], '', 1)
    assert new_registry.count('"enumerate 사용": "create_safe_enumerate"') == 1
    new_plan = old_plan.replace(
        '    # do not add syntax tags beyond the existing 19-tag storage policy.',
        '    # add only enumerate; other metric preferences exist in batches 3/5.'
    )
    for line in (
        '        ("복합 할당", "aug_assign_count", "create_safe_augassign"),\n',
        '        ("키워드 인자 사용", "keyword_arg_count", "create_safe_keyword_call"),\n',
    ):
        if new_plan.count(line) != 1:
            raise RepairError('10차 중복 계획 패턴 예상 불일치: ' + line.strip())
        new_plan = new_plan.replace(line, '', 1)
    return old_registry, new_registry, old_plan, new_plan


def preflight(root: Path) -> list[Change]:
    root = root.resolve()
    if not (root / '.git').is_dir() or not (root / 'backend/app/services').is_dir():
        raise RepairError('capstone_main 프로젝트 최상위 디렉터리에서 실행해야 합니다.')
    installer_path = root / ORIGINAL_INSTALLER
    if not installer_path.is_file() or _digest_lf(installer_path.read_bytes()) != B10_INSTALLER_SHA:
        raise RepairError('원래 10차 설치기 버전이 예상과 다릅니다. 중단합니다.')
    installer_source = installer_path.read_text(encoding='utf-8-sig')
    old_registry, new_registry, old_plan, new_plan = _expected_blocks(installer_source)

    dispatch_path = root / DISPATCH
    if not dispatch_path.is_file():
        raise RepairError('스타일 변환 실행기 파일을 찾을 수 없습니다.')
    dispatch = dispatch_path.read_text(encoding='utf-8-sig')
    for action in (*EXISTING.values(), *NEW_TAG.values()):
        if f'"{action}"' not in dispatch:
            raise RepairError('기존/신규 변환 액션의 실행기 연결을 확인할 수 없습니다: ' + action)

    changes: list[Change] = []
    for path, old_block, new_block in (
        (REGISTRY, old_registry, new_registry),
        (PLAN, old_plan, new_plan),
    ):
        target = root / path
        if not target.is_file():
            raise RepairError('대상 파일 누락: ' + str(path))
        original = target.read_bytes()
        text, bom, crlf = _decode(original)
        after = _patch_block(text, old_block, new_block, str(path))
        ast.parse(after, filename=str(path))
        if path == REGISTRY:
            before_pairs = _registry_pairs(text)
            after_pairs = _registry_pairs(after)
            counts = {name: sum(key == name for key, _ in before_pairs)
                      for name in {*EXISTING, *NEW_TAG}}
            if after == text:
                if any(count != 1 for count in counts.values()):
                    raise RepairError('이미 수정된 레지스트리의 태그 중복 상태가 잘못되었습니다.')
            else:
                if any(count != 2 for name, count in counts.items() if name in EXISTING):
                    raise RepairError('기존 4개 태그가 기대한 형태로 중복되지 않았습니다.')
                if counts['enumerate 사용'] != 1:
                    raise RepairError('enumerate 연결 상태가 예상과 다릅니다.')
            all_keys = [key for key, _ in after_pairs]
            if len(all_keys) != len(set(all_keys)):
                raise RepairError('수정 후에도 중복 태그가 남아 있습니다. 다른 파일은 변경하지 않았습니다.')
            mapping = dict(after_pairs)
            for name, action in {**EXISTING, **NEW_TAG}.items():
                if mapping.get(name) != action:
                    raise RepairError(f'수정 후 액션 불일치: {name} -> {mapping.get(name)!r}')
            if len(after_pairs) != 69:
                raise RepairError(f'연결 태그 수 불일치: {len(after_pairs)} (예상 69).')
        if after != text:
            changes.append(Change(target, original, _encode(after, bom, crlf)))

    for path, old_digest, new_digest, payload_name in (
        (TEST, OLD_TEST_SHA, NEW_TEST_SHA, 'test_style_unmapped_patterns_batch10_integration.py.source'),
        (AUDIT, OLD_AUDIT_SHA, NEW_AUDIT_SHA, 'audit_transform_three_patterns_batch10.py.source'),
    ):
        target = root / path
        payload = PAYLOAD_DIR / payload_name
        if not target.is_file() or not payload.is_file():
            raise RepairError('테스트/전수 검사 파일 누락: ' + str(path))
        original = target.read_bytes()
        digest = _digest_lf(original)
        updated = payload.read_bytes()
        if sha256(updated).hexdigest() != new_digest:
            raise RepairError('수정용 패키지의 무결성 확인 실패: ' + payload_name)
        ast.parse(updated.decode('utf-8'), filename=str(path))
        if digest == new_digest:
            continue
        if digest != old_digest:
            raise RepairError('대상 파일이 예상과 다르므로 덮어쓰지 않습니다: ' + str(path))
        _, bom, crlf = _decode(original)
        changes.append(Change(target, original, _encode(updated.decode('utf-8'), bom, crlf)))
    return changes


def _atomic_write(path: Path, content: bytes) -> None:
    with tempfile.NamedTemporaryFile('wb', dir=path.parent, prefix='.capstone_fix10_', suffix='.tmp', delete=False) as fp:
        temp = Path(fp.name)
        fp.write(content)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def install(root: Path) -> int:
    changes = preflight(root)
    if not changes:
        print('10차 중복 매핑 수정이 이미 설치되었습니다. 변경 사항이 없습니다.')
        return 0
    folder = root.resolve() / '.git' / 'capstone_batch10_duplicate_fix_backups' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True, exist_ok=False)
    for change in changes:
        backup = folder / change.path.relative_to(root.resolve())
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(change.original)
    applied: list[Change] = []
    try:
        for change in changes:
            if change.path.read_bytes() != change.original:
                raise RepairError('사전 검사 후 변경된 파일 감지: ' + str(change.path))
            _atomic_write(change.path, change.updated)
            applied.append(change)
        if preflight(root):
            raise RepairError('설치 후 재검사에서 변경 예정 파일이 남았습니다.')
    except (OSError, RepairError) as error:
        for change in reversed(applied):
            try:
                _atomic_write(change.path, change.original)
            except OSError:
                pass
        raise RepairError('설치 검증 실패로 변경 파일 복원 시도: ' + str(error)) from error
    print(f'10차 중복 연결 오류 수정 완료: {len(changes)}개 파일. 백업: {folder}')
    print('기존 4개 태그 연결 유지, enumerate 1개 신규 연결, frontend 변경 없음.')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        if args.check:
            changes = preflight(args.root)
            print(f'사전 검사 통과: {len(changes)}개 파일 수정 예정')
            for c in changes:
                print(' -', c.path.relative_to(args.root.resolve()))
            return 0
        return install(args.root)
    except (RepairError, OSError, UnicodeError, SyntaxError, ValueError) as error:
        print('수정 중단:', error, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
