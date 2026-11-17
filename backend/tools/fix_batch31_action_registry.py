"""Repair Batch31's seven registry links so static and runtime audits agree.

From capstone_main root (PowerShell):
  python backend\\tools\\fix_batch31_action_registry.py --check
  python backend\\tools\\fix_batch31_action_registry.py

Only changes backend/app/services/style_apply_service.py and
backend/tests/test_style_batch26_new_links.py. No frontend changes.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPLY = Path('backend/app/services/style_apply_service.py')
TEST = Path('backend/tests/test_style_batch26_new_links.py')
SERVICE = Path('backend/app/services/improvement/safe_batch31_service.py')
BACKUP = Path('.git/capstone_batch31_registry_hotfix_backup')
MARK = 'CAPSTONE_BATCH31_STATIC_DISPATCH_FIX_V1'

# Public action name -> real callable exported by the existing Batch31 module.
ACTIONS = (
    ('create_safe_closed_default_parameter', 'transform_default_parameter'),
    ('create_safe_closed_varargs', 'transform_varargs_parameter'),
    ('create_safe_closed_kwargs', 'transform_kwargs_parameter'),
    ('create_safe_closed_async_definition', 'transform_async_function_definition'),
    ('create_safe_closed_await', 'transform_async_await'),
    ('create_safe_closed_async_structure', 'transform_async_processing_structure'),
    ('create_safe_closed_long_function', 'transform_long_function_structure'),
)


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: 예상한 원본 코드가 정확히 1회여야 합니다. 발견: {count}')
    return text.replace(old, new, 1)


def _read(path: Path):
    raw = path.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    body = raw[3:] if bom else raw
    if b'\r\n' in body and b'\n' in body.replace(b'\r\n', b''):
        raise RuntimeError(f'{path}: CRLF/LF 혼합 줄바꿈을 수정하지 않습니다.')
    if b'\r' in body.replace(b'\r\n', b''):
        raise RuntimeError(f'{path}: 잘못된 CR 줄바꿈을 수정하지 않습니다.')
    eol = '\r\n' if b'\r\n' in body else '\n'
    return body.replace(b'\r\n', b'\n').decode('utf-8'), raw, eol, bom


def _encode(content: str, eol: str, bom: bool) -> bytes:
    return (b'\xef\xbb\xbf' if bom else b'') + content.replace('\n', eol).encode('utf-8')


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.batch31_registry_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def patch_dispatch(src: str) -> str:
    if 'CAPSTONE_BATCH31_DISPATCH_IMPORT_V1' not in src:
        raise RuntimeError('31차 설치가 확인되지 않습니다. 기존 설치를 다시 실행하지 마세요.')
    if 'CAPSTONE_BATCH31_DISPATCH_MAP_V1' not in src:
        raise RuntimeError('31차 변환 맵 표시가 없어 수정을 중단합니다.')
    old_import = ('# CAPSTONE_BATCH31_DISPATCH_IMPORT_V1\n'
                  'from app.services.improvement.safe_batch31_service import TRANSFORMERS as BATCH31_TRANSFORMERS\n')
    new_import = (
        '# CAPSTONE_BATCH31_DISPATCH_IMPORT_V1\n'
        'from app.services.improvement.safe_batch31_service import (\n'
        + ''.join(f'    {fn},\n' for _, fn in ACTIONS)
        + ')\n'
    )
    src = _replace_once(src, old_import, new_import, '31차 변환기 import')
    marker = '        # CAPSTONE_BATCH31_DISPATCH_MAP_V1\n'
    additions = (f'        # {MARK}: 정적 감사와 실제 변환기가 동일한 등록표를 공유합니다.\n'
                 + ''.join(f'        "{action}": {fn},\n' for action, fn in ACTIONS))
    src = _replace_once(src, marker, marker + additions, '31차 action_map')
    src = _replace_once(src,
        '    return action_map.get(action) or BATCH31_TRANSFORMERS.get(action)\n',
        '    return action_map.get(action)\n',
        '31차 동적 fallback 제거')
    _validate_static_dispatch(src)
    return src


def _validate_static_dispatch(src: str) -> None:
    """Same essential AST rules used by style_transform_audit_service."""
    tree = ast.parse(src)
    symbols = {alias.asname or alias.name
               for stmt in tree.body if isinstance(stmt, (ast.Import, ast.ImportFrom))
               for alias in stmt.names}
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name == '_get_transform_function']
    if len(functions) != 1:
        raise RuntimeError('31차 dispatcher 함수가 정확히 하나여야 합니다.')
    dicts = [n.value for n in ast.walk(functions[0])
             if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict)
             and any(isinstance(t, ast.Name) and t.id == 'action_map' for t in n.targets)]
    if len(dicts) != 1:
        raise RuntimeError('31차 action_map 딕셔너리가 정확히 하나여야 합니다.')
    mapping = {}
    for k, v in zip(dicts[0].keys, dicts[0].values):
        if not (isinstance(k, ast.Constant) and isinstance(k.value, str)
                and isinstance(v, ast.Name)):
            raise RuntimeError('정적 action_map 항목 형태가 올바르지 않습니다.')
        if k.value in mapping:
            raise RuntimeError(f'중복 action_map 항목: {k.value}')
        mapping[k.value] = v.id
    for action, fn in ACTIONS:
        if mapping.get(action) != fn or fn not in symbols:
            raise RuntimeError(f'31차 액션 연결 검증 실패: {action}')


def patch_legacy_test(src: str) -> str:
    """Update only the known Batch26 status test.

    Batch27 corrected the file I/O assertion from assertIn to assertNotIn.
    Older local copies may retain assertIn, so accept exactly these two
    known variants rather than requiring one outdated byte-for-byte block.
    """
    prefix = (
        '    def test_previous_unmapped_tags_stay_compare_only(self):\n'
        "        self.assertIn('기본 매개변수', COMPARE_ONLY_TAGS)\n"
        "        self.assertIn('비동기 함수 정의', COMPARE_ONLY_TAGS)\n"
    )
    variants = (
        prefix + "        self.assertNotIn('파일 입출력 구조', COMPARE_ONLY_TAGS)\n",
        prefix + "        self.assertIn('파일 입출력 구조', COMPARE_ONLY_TAGS)\n",
    )
    after = (
        '    def test_previous_unmapped_tags_now_have_guarded_links(self):\n'
        '        # CAPSTONE_BATCH31_LEGACY_STATUS_FIX_V2: 현재 태그 연결 상태 기준.\n'
        "        for tag in ('기본 매개변수', '비동기 함수 정의', '파일 입출력 구조'):\n"
        '            with self.subTest(tag=tag):\n'
        '                self.assertIn(tag, CREATE_ACTION_BY_TAG)\n'
        '                self.assertNotIn(tag, COMPARE_ONLY_TAGS)\n'
    )
    matches = [(variant, src.count(variant)) for variant in variants]
    if sum(count for _variant, count in matches) != 1:
        raise RuntimeError(
            '26차 구형 테스트 상태: 알려진 원본 형태가 정확히 1회여야 합니다. '
            + f'일치 횟수: {sum(count for _variant, count in matches)}'
        )
    matched = next(variant for variant, count in matches if count == 1)
    return src.replace(matched, after, 1)


def preflight(root: Path):
    if not (root / '.git').is_dir():
        raise RuntimeError('capstone_main Git 저장소 루트에서 실행해 주세요.')
    for path in (APPLY, TEST, SERVICE):
        if not (root / path).is_file():
            raise RuntimeError(f'필수 파일이 없습니다: {path}')
    src, original_apply, eol_apply, bom_apply = _read(root / APPLY)
    legacy, original_test, eol_test, bom_test = _read(root / TEST)
    transform_src, _, _, _ = _read(root / SERVICE)

    # Ensure the installed Batch31 payload still provides these functions.
    ast_tree = ast.parse(transform_src)
    functions = {n.name for n in ast_tree.body if isinstance(n, ast.FunctionDef)}
    if any(fn not in functions for _, fn in ACTIONS):
        raise RuntimeError('31차 변환기 함수가 누락되어 수정을 중단합니다.')
    if 'CAPSTONE_BATCH31_STATIC_DISPATCH_FIX_V1' in src:
        if 'CAPSTONE_BATCH31_LEGACY_STATUS_FIX_V2' not in legacy:
            raise RuntimeError('부분 적용 상태를 감지했습니다. 설치를 중단합니다.')
        _validate_static_dispatch(src)
        return {}, {}, True
    if 'CAPSTONE_BATCH31_LEGACY_STATUS_FIX_V2' in legacy:
        raise RuntimeError('부분 적용 상태를 감지했습니다. 설치를 중단합니다.')
    patched_apply = patch_dispatch(src)
    patched_test = patch_legacy_test(legacy)
    ast.parse(patched_apply)
    ast.parse(patched_test)
    originals = {APPLY: original_apply, TEST: original_test}
    updates = {APPLY: _encode(patched_apply, eol_apply, bom_apply),
               TEST: _encode(patched_test, eol_test, bom_test)}
    # Check stable backup destinations before touching anything.
    for rel, raw in originals.items():
        dest = root / BACKUP / rel
        if dest.exists() and dest.read_bytes() != raw:
            raise RuntimeError(f'기존 백업과 파일이 달라 중단합니다: {dest}')
    return originals, updates, False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='검사만 하고 파일은 수정하지 않습니다.')
    args = parser.parse_args()
    try:
        originals, updates, already = preflight(ROOT)
        if already:
            print('31차 액션 등록 수정이 이미 적용되어 있습니다. 변경할 파일이 없습니다.')
            return 0
        if args.check:
            print('31차 액션 등록 사전 검사 통과: 2개 파일, 7개 정적 액션, 프론트엔드 변경 없음')
            return 0
        for rel, raw in originals.items():
            dest = ROOT / BACKUP / rel
            if not dest.exists():
                _write_atomic(dest, raw)
        done = []
        try:
            for rel, updated in updates.items():
                _write_atomic(ROOT / rel, updated)
                done.append(rel)
        except Exception:
            for rel in reversed(done):
                _write_atomic(ROOT / rel, originals[rel])
            raise
        print('31차 액션 등록 수정 완료: 누락된 7개 정적 등록 및 26차 이전 테스트 갱신')
        print('기존 2272개 전체 테스트 및 31차 감사 도구를 다시 실행해 주세요.')
        return 0
    except (OSError, RuntimeError, UnicodeError, SyntaxError, ValueError) as err:
        print(f'31차 수정 중단 (원본 유지): {err}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
