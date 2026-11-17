"""Fix Batch28 provenance loss caused by resolving duplicate actions too early.

Run from capstone_main root (Windows PowerShell):
    python backend/tools/fix_batch28_policy_sources.py --check
    python backend/tools/fix_batch28_policy_sources.py

Only modifies backend/app/services/style_transform_plan_service.py.
Frontend, saved styles, registry and tested transformers are unchanged.
"""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TARGET = Path('backend/app/services/style_transform_plan_service.py')
BACKUP = Path('.git/capstone_batch28_policy_sources_backup/style_transform_plan_service.py')

# The existing Batch28 plan finalizer already records both source tags, but
# _resolve_new_family_actions() discards duplicate actions before it runs.
# Finalizing a second time is intentionally retained: it is idempotent and
# preserves existing family-conflict, direction, and action-selection logic.
BEFORE = (
    '                _resolve_dictionary_actions(_resolve_collection_actions(actions))\n'
)
AFTER = (
    '                _resolve_dictionary_actions(_resolve_collection_actions('
    'finalize_tag_action_policies(actions)))\n'
)
REQUIRED = (
    'CAPSTONE_BATCH28_PLAN_FINALIZE_V1',
    'from app.services.style_tag_action_policy_service import finalize_tag_action_policies',
    '"actions": finalize_tag_action_policies(',
    '"compare_only": sorted(set(compare_only))',
)


def read_source(path: Path):
    raw = path.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    body = raw[3:] if bom else raw
    if b'\r\n' in body and b'\n' in body.replace(b'\r\n', b''):
        raise RuntimeError('Mixed CRLF and LF line endings: refusing edit')
    if b'\r' in body.replace(b'\r\n', b''):
        raise RuntimeError('Bare CR line endings: refusing edit')
    eol = '\r\n' if b'\r\n' in body else '\n'
    text = body.replace(b'\r\n', b'\n').decode('utf-8')
    return text, raw, eol, bom


def prepare(root: Path):
    if not (root / '.git').is_dir():
        raise RuntimeError('Not a Git working tree: run from capstone_main')
    path = root / TARGET
    if not path.is_file():
        raise RuntimeError(f'Missing target: {TARGET}')
    source, original, eol, bom = read_source(path)
    if any(token not in source for token in REQUIRED):
        raise RuntimeError('Expected Batch28 installation markers are missing')
    if source.count(AFTER) == 1 and BEFORE not in source:
        return None, original, 'already'
    if source.count(BEFORE) != 1 or AFTER in source:
        raise RuntimeError('Unexpected Batch28 plan content; no changes made')
    changed = source.replace(BEFORE, AFTER, 1)
    ast.parse(changed)
    if changed.count(AFTER) != 1 or changed.count(BEFORE) != 0:
        raise RuntimeError('Invalid target replacement; no changes made')
    output = (b'\xef\xbb\xbf' if bom else b'') + changed.replace('\n', eol).encode('utf-8')
    return output, original, 'ready'


def atomic_write(path: Path, data: bytes):
    fd, tmp = tempfile.mkstemp(prefix='.capstone_b28_fix_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def install(root: Path = ROOT, check: bool = False) -> str:
    output, original, status = prepare(root)
    if status == 'already':
        return '28차 출처 보존 수정이 이미 적용되어 있습니다. 변경 없음.'
    if check:
        return '28차 출처 보존 수정 사전 검사 통과. 파일을 변경하지 않았습니다.'
    backup_path = root / BACKUP
    if backup_path.exists():
        raise RuntimeError('Backup already exists; refusing overwrite')
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    # The backup lives under .git, never appears in git status.
    backup_path.write_bytes(original)
    try:
        atomic_write(root / TARGET, output)
    except Exception:
        atomic_write(root / TARGET, original)
        raise
    return '28차 출처 보존 수정 완료: 변환 계획 처리 순서만 수정했습니다.'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate without changing files')
    args = parser.parse_args()
    try:
        print(install(check=args.check))
        return 0
    except (RuntimeError, OSError, UnicodeError, SyntaxError, ValueError) as exc:
        print(f'28차 수정 중단: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
