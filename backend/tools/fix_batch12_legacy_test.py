"""Compatibility fix for Batch 11 registry test after Batch 12 expands tag links.

Run from repository root:
    python backend/tools/fix_batch12_legacy_test.py --check
    python backend/tools/fix_batch12_legacy_test.py

Only the one obsolete count assertion test is modified. A backup is stored in
.git/. This does not change runtime transformations, tag rules, or registry.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime
import os
from pathlib import Path
import sys
import tempfile

TARGET = Path('backend/tests/test_style_unmapped_patterns_batch11_integration.py')
REGISTRY = Path('backend/app/services/style_tag_transform_map_service.py')
OLD = '''    def test_unique_registry_72_and_30_remaining(self):
        tree = ast.parse(Path(mapping.__file__).read_text(encoding='utf-8-sig'))
        registers = [node.value for node in tree.body
                     if isinstance(node, ast.AnnAssign)
                     and isinstance(node.target, ast.Name)
                     and node.target.id == 'CREATE_ACTION_BY_TAG']
        self.assertEqual(len(registers), 1)
        keys = [node.value for node in registers[0].keys]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(keys), 72)
        self.assertEqual(len(mapping.COMPARE_ONLY_TAGS), 30)
'''
NEW = '''    def test_unique_registry_preserves_batch11_baseline(self):
        # This is a Batch 11 regression test. Later batches may add links;
        # ensure no existing Batch 11 registration was removed instead of
        # freezing the registry size at 72 indefinitely.
        tree = ast.parse(Path(mapping.__file__).read_text(encoding='utf-8-sig'))
        registers = [node.value for node in tree.body
                     if isinstance(node, ast.AnnAssign)
                     and isinstance(node.target, ast.Name)
                     and node.target.id == 'CREATE_ACTION_BY_TAG']
        self.assertEqual(len(registers), 1)
        keys = [node.value for node in registers[0].keys]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertGreaterEqual(len(keys), 72)
        self.assertEqual(set(keys), set(mapping.CREATE_ACTION_BY_TAG))
        all_tags = set(mapping.SYNTAX_TAG_RULES) | set(mapping.CONCEPT_TAG_RULES)
        self.assertTrue(set(keys) <= all_tags)
        self.assertEqual(mapping.COMPARE_ONLY_TAGS, all_tags - set(keys))
        self.assertEqual(len(keys) + len(mapping.COMPARE_ONLY_TAGS), len(all_tags))
'''


def _parse_registry(text: str) -> dict[str, str]:
    tree = ast.parse(text)
    nodes = [n.value for n in tree.body if isinstance(n, ast.AnnAssign)
             and isinstance(n.target, ast.Name) and n.target.id == 'CREATE_ACTION_BY_TAG']
    if len(nodes) != 1 or not isinstance(nodes[0], ast.Dict):
        raise ValueError('등록 태그 딕셔너리를 확인할 수 없습니다.')
    entries = []
    for key, val in zip(nodes[0].keys, nodes[0].values):
        if not (isinstance(key, ast.Constant) and type(key.value) is str
                and isinstance(val, ast.Constant) and type(val.value) is str):
            raise ValueError('태그 등록 형식이 예상과 다릅니다.')
        entries.append((key.value, val.value))
    if len(set(k for k, _ in entries)) != len(entries):
        raise ValueError('태그 등록에 중복이 있습니다.')
    return dict(entries)


def _root_check(root: Path) -> None:
    if not (root / '.git').exists():
        raise ValueError('capstone_main 프로젝트 최상위 폴더에서 실행해 주세요.')
    if not (root / TARGET).is_file() or not (root / REGISTRY).is_file():
        raise ValueError('필요한 11차 테스트 또는 변환 태그 파일이 없습니다.')
    registry = _parse_registry((root / REGISTRY).read_text(encoding='utf-8-sig'))
    expected_12 = {'continue문': 'create_safe_guard_continue',
                   '식별 비교': 'create_safe_literal_identity',
                   '산술 연산': 'create_safe_arithmetic_expression'}
    if len(registry) < 75 or any(registry.get(k) != v for k, v in expected_12.items()):
        raise ValueError('12차 패치가 적용된 레지스트리가 아닙니다. 수정을 중단합니다.')


def _updated(data: bytes) -> tuple[bytes, bool]:
    bom = data.startswith(b'\xef\xbb\xbf')
    body = data[3:] if bom else data
    crlf = b'\r\n' in body
    text = body.decode('utf-8').replace('\r\n', '\n')
    if NEW in text:
        if OLD in text or text.count(NEW) != 1:
            raise ValueError('테스트가 중복/부분 수정되었습니다.')
        return data, False
    if text.count(OLD) != 1:
        raise ValueError('11차 테스트가 예상 버전과 다릅니다. 자동 수정하지 않습니다.')
    changed = text.replace(OLD, NEW, 1)
    ast.parse(changed, filename=str(TARGET))
    new_body = changed.replace('\n', '\r\n') if crlf else changed
    return ((b'\xef\xbb\xbf' if bom else b'') + new_body.encode('utf-8')), True


def _atomic_write(path: Path, data: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.capstone_legacy_fix_',
                                     suffix='.tmp', delete=False) as f:
        tmp = Path(f.name)
        f.write(data)
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        _root_check(root)
        path = root / TARGET
        original = path.read_bytes()
        replacement, needed = _updated(original)
        if not needed:
            print('11차/12차 테스트 호환성 수정이 이미 적용되었습니다.')
            return 0
        if args.check:
            print('사전 검사 통과: 11차 테스트의 고정 개수 검사를 버전 호환 검사로 수정할 수 있습니다.')
            print('수정 대상:', TARGET)
            return 0
        backup = (root / '.git' / ('capstone_batch12_legacy_test_'
                  + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.bak'))
        backup.write_bytes(original)
        try:
            if path.read_bytes() != original:
                raise RuntimeError('수정 중 테스트 파일이 변경되었습니다.')
            _atomic_write(path, replacement)
            after, needed_after = _updated(path.read_bytes())
            if needed_after or after != replacement:
                raise RuntimeError('수정 후 검사가 실패했습니다.')
        except Exception:
            _atomic_write(path, original)
            raise
        print('12차 호환성 수정 완료:', TARGET)
        print('백업:', backup)
        print('실제 변환 로직 및 기존 태그 매핑은 변경하지 않았습니다.')
        return 0
    except (OSError, ValueError, SyntaxError, RuntimeError, UnicodeError) as e:
        print('자동 수정 중단:', e, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
