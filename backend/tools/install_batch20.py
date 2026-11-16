"""Batch 20 safe None/print transformations (based on GitHub main 5785c7f).

From capstone_main project root:
  python backend/tools/install_batch20.py --check
  python backend/tools/install_batch20.py
"""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = Path('backend/tools/batch20_payload')
TARGETS = (
    Path('backend/app/services/style_tag_transform_map_service.py'),
    Path('backend/app/services/style_transform_plan_service.py'),
    Path('backend/app/services/style_apply_service.py'),
)
NEW = {
    Path('backend/app/services/improvement/safe_batch20_service.py'):
        PAYLOAD / 'safe_batch20_service.py.source',
    Path('backend/tests/test_style_batch20_new_links.py'):
        PAYLOAD / 'test_style_batch20_new_links.py.source',
    Path('backend/tools/audit_transform_batch20.py'):
        PAYLOAD / 'audit_transform_batch20.py.source',
}
MARK = 'CAPSTONE_BATCH20_'


def _replace_once(source: str, before: str, after: str, label: str) -> str:
    count = source.count(before)
    if count != 1:
        raise RuntimeError(f'{label}: expected one anchor, found {count}.')
    return source.replace(before, after, 1)


def _registry_keys(source: str) -> list[str]:
    tree = ast.parse(source)
    nodes = [n.value for n in tree.body if isinstance(n, ast.AnnAssign)
             and isinstance(n.target, ast.Name)
             and n.target.id == 'CREATE_ACTION_BY_TAG']
    if len(nodes) != 1 or not isinstance(nodes[0], ast.Dict):
        raise RuntimeError('Mapping declaration is not a single static dictionary.')
    keys = [k.value for k in nodes[0].keys if isinstance(k, ast.Constant)
            and isinstance(k.value, str)]
    if len(keys) != len(nodes[0].keys) or len(keys) != len(set(keys)):
        raise RuntimeError('Invalid or duplicated tag registry keys.')
    return keys


def patch_registry(source: str) -> str:
    old_keys = _registry_keys(source)
    if '# CAPSTONE_BATCH20_REGISTRY_V1' in source:
        if len(old_keys) != 82 or not {'None 사용', 'print 사용'}.issubset(old_keys):
            raise RuntimeError('Partial Batch20 tag registration.')
        return source
    if len(old_keys) != 80 or 'None 사용' in old_keys or 'print 사용' in old_keys:
        raise RuntimeError(f'Expected Batch19 registry with 80 mappings, got {len(old_keys)}.')
    source = _replace_once(source,
        'CREATE_ACTION_BY_TAG: dict[str, str] = {\n',
        'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
        '    # CAPSTONE_BATCH20_REGISTRY_V1: narrowly safe formatting of literal/call forms.\n'
        '    "None 사용": "create_safe_empty_dict_none",\n'
        '    "print 사용": "create_safe_builtin_print",\n',
        'registry header')
    if len(_registry_keys(source)) != 82:
        raise RuntimeError('Registry size changed unexpectedly after patch.')
    return source


def patch_plan(source: str) -> str:
    if '# CAPSTONE_BATCH20_METRIC_PLAN_V1' in source:
        if 'create_safe_empty_dict_none' not in source or 'create_safe_builtin_print' not in source:
            raise RuntimeError('Partial Batch20 plan.')
        return source
    if '# CAPSTONE_BATCH19_METRIC_GATE_V1' not in source:
        raise RuntimeError('Batch19 planning gate is missing.')
    gate = '''    # CAPSTONE_BATCH20_METRIC_PLAN_V1: only observed style preferences.
    saved_b20 = _get_style_metrics(diff)
    target_b20 = _get_target_metrics(diff)
    for tag_b20, saved_metric, target_evidence, action_b20 in (
        ("None 사용", "none_count", ("dict_literal_count", "attribute_count", "call_count"),
         "create_safe_empty_dict_none"),
        ("print 사용", "print_call_count", ("import_count", "attribute_count", "call_count"),
         "create_safe_builtin_print"),
    ):
        if (_metric_count(saved_b20, saved_metric) > 0
                and _metric_count(target_b20, saved_metric) == 0
                and all(_metric_count(target_b20, metric) > 0 for metric in target_evidence)
                and not any(item.get("action") == action_b20 for item in actions)):
            actions.append({
                "tag": tag_b20,
                "action": action_b20,
                "reason": "저장 스타일의 기존 메트릭이 확인된 경우 안전한 국소 코드 패턴만 변경합니다.",
            })

'''
    source = _replace_once(source,
        '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n',
        gate+'    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n',
        'plan placement')
    source = _replace_once(source,
        '        if tag_name in {"비교 연산", "함수 호출"}:\n'
        '            continue  # Batch 19: metric gate above is required.\n',
        '        if tag_name in {"비교 연산", "함수 호출"}:\n'
        '            continue  # Batch 19: metric gate above is required.\n'
        '        # CAPSTONE_BATCH20_METRIC_ONLY_V1: missing-tag evidence alone is insufficient.\n'
        '        if tag_name in {"None 사용", "print 사용"}:\n'
        '            continue\n',
        'metric-only guard')
    ast.parse(source)
    return source


def patch_dispatch(source: str) -> str:
    if '# CAPSTONE_BATCH20_DISPATCH_IMPORT_V1' in source:
        if ('"create_safe_empty_dict_none": transform_safe_empty_dict_get_to_none' not in source
                or '"create_safe_builtin_print": transform_safe_builtins_print_to_print' not in source):
            raise RuntimeError('Partial Batch20 dispatcher.')
        return source
    if '# CAPSTONE_BATCH19_DISPATCH_IMPORT_V1' not in source:
        raise RuntimeError('Batch19 dispatcher import is missing.')
    source = _replace_once(source,
        'def _get_transform_function(action: str):\n',
        '# CAPSTONE_BATCH20_DISPATCH_IMPORT_V1\n'
        'from app.services.improvement.safe_batch20_service import (\n'
        '    transform_safe_empty_dict_get_to_none,\n'
        '    transform_safe_builtins_print_to_print,\n'
        ')\n\n'
        'def _get_transform_function(action: str):\n',
        'dispatcher import')
    source = _replace_once(source,
        '        "create_safe_operator_comparison": transform_operator_comparison_to_syntax,\n',
        '        "create_safe_operator_comparison": transform_operator_comparison_to_syntax,\n'
        '        # CAPSTONE_BATCH20_DISPATCH_MAP_V1\n'
        '        "create_safe_empty_dict_none": transform_safe_empty_dict_get_to_none,\n'
        '        "create_safe_builtin_print": transform_safe_builtins_print_to_print,\n',
        'dispatcher mapping')
    ast.parse(source)
    return source


PATCHERS = dict(zip(TARGETS, (patch_registry, patch_plan, patch_dispatch)))


def _read(path: Path):
    data = path.read_bytes()
    bom = data.startswith(b'\xef\xbb\xbf')
    content = data.decode('utf-8-sig')
    if '\r\n' in content and '\n' in content.replace('\r\n', ''):
        raise RuntimeError(f'Mixed line endings: {path}')
    eol = '\r\n' if '\r\n' in content else '\n'
    return content.replace('\r\n', '\n'), eol, bom


def _encode(source: str, eol: str, bom: bool):
    return (b'\xef\xbb\xbf' if bom else b'') + source.replace('\n', eol).encode('utf-8')


def prepare(root: Path) -> dict[Path, bytes]:
    changed = {}
    statuses = []
    for relative, fn in PATCHERS.items():
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f'Missing expected project file: {relative}')
        source, eol, bom = _read(path)
        new = fn(source)
        statuses.append(new != source)
        if new != source:
            changed[relative] = _encode(new, eol, bom)
    for relative, payload in NEW.items():
        source_path = root / payload
        if not source_path.is_file():
            raise RuntimeError(f'Missing ZIP payload: {payload}')
        data = source_path.read_bytes()
        if not data.endswith(b'\n') or b'\r' in data:
            raise RuntimeError(f'Invalid payload formatting: {payload}')
        compile(data, str(relative), 'exec')
        dest = root / relative
        if dest.exists():
            if dest.read_bytes() != data:
                raise RuntimeError(f'Conflicting file: {relative}')
            statuses.append(False)
        else:
            changed[relative] = data
            statuses.append(True)
    if any(statuses) and not all(statuses):
        raise RuntimeError('Partial Batch20 installation. Nothing was modified.')
    return changed


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, file_name = tempfile.mkstemp(prefix='.capstone_b20_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        os.replace(file_name, path)
    finally:
        if os.path.exists(file_name):
            os.unlink(file_name)


def install(root: Path, check: bool = False) -> str:
    if not (root / '.git').is_dir():
        raise RuntimeError('Git project folder (.git) not found.')
    changes = prepare(root)
    if not changes:
        return 'Batch 20 already installed; no changes.'
    if check:
        return f'Batch20 preflight passed: {len(changes)} files; no files modified.'
    originals = {name: (root / name).read_bytes() if (root / name).is_file() else None
                 for name in changes}
    backups = root / '.git' / 'capstone_batch20_backups'
    for name, old in originals.items():
        if old is None:
            continue
        backup = backups / name
        if backup.exists() and backup.read_bytes() != old:
            raise RuntimeError(f'Conflicting backup: {name}')
    for name, old in originals.items():
        if old is not None:
            backup = backups / name
            if not backup.exists():
                _atomic_write(backup, old)
    completed = []
    try:
        for name, content in changes.items():
            _atomic_write(root / name, content)
            completed.append(name)
    except Exception:
        for name in reversed(completed):
            if originals[name] is None:
                (root / name).unlink(missing_ok=True)
            else:
                _atomic_write(root / name, originals[name])
        raise
    return f'Installed Batch 20: {len(changes)} files; None and print safe actions.'


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    try:
        print(install(ROOT, args.check))
        return 0
    except (RuntimeError, OSError, ValueError, SyntaxError, UnicodeError) as exc:
        print(f'Batch20 installation stopped: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
