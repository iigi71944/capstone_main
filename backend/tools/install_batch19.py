"""Batch 19 installer: remove redundant strict UI, link two safe transform tags.

Run from repository root:
  python backend/tools/install_batch19.py --check
  python backend/tools/install_batch19.py

Requires batches 16, 17 and 18 already installed locally. No GitHub writes.
"""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MARK = 'CAPSTONE_BATCH19_'
PAYLOAD = Path('backend/tools/batch19_payload')
TARGETS = (
    Path('backend/app/services/style_tag_transform_map_service.py'),
    Path('backend/app/services/style_transform_plan_service.py'),
    Path('backend/app/services/style_apply_service.py'),
    Path('backend/tests/test_style_unmapped_patterns_batch13_integration.py'),
    Path('frontend/components/sections/StyleApplySection.tsx'),
)
NEW = {
    Path('backend/app/services/improvement/safe_comparison_batch19_service.py'):
        PAYLOAD / 'safe_comparison_batch19_service.py.source',
    Path('backend/tests/test_style_batch19_new_links.py'):
        PAYLOAD / 'test_style_batch19_new_links.py.source',
    Path('backend/tools/audit_transform_batch19.py'):
        PAYLOAD / 'audit_transform_batch19.py.source',
}


def _replace_once(s: str, old: str, new: str, label: str) -> str:
    if s.count(old) != 1:
        raise RuntimeError(f'{label}: expected one anchor; found {s.count(old)}.')
    return s.replace(old, new, 1)


def _validate_registry(s: str) -> None:
    tree = ast.parse(s)
    entries = [item.value for item in tree.body
               if isinstance(item, ast.AnnAssign)
               and isinstance(item.target, ast.Name)
               and item.target.id == 'CREATE_ACTION_BY_TAG']
    if len(entries) != 1 or not isinstance(entries[0], ast.Dict):
        raise RuntimeError('Registry structure is unknown.')
    keys = [key.value for key in entries[0].keys if isinstance(key, ast.Constant)]
    if len(keys) != 80 or len(keys) != len(set(keys)):
        raise RuntimeError(f'Registry has {len(keys)} links; expected 80 unique links.')
    if keys.count('비교 연산') != 1 or keys.count('함수 호출') != 1:
        raise RuntimeError('New mapping keys are missing or duplicated.')


def patch_registry(s: str) -> str:
    marker = '# CAPSTONE_BATCH19_REGISTRY_V1'
    if marker in s:
        _validate_registry(s)
        return s
    if '    "비교 연산":' in s or '    "함수 호출":' in s:
        raise RuntimeError('New tags already have other mappings; refusing to replace them.')
    s = _replace_once(
        s, 'CREATE_ACTION_BY_TAG: dict[str, str] = {\n',
        'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
        '    # CAPSTONE_BATCH19_REGISTRY_V1: narrow operator conversions.\n'
        '    "비교 연산": "create_safe_operator_comparison",\n'
        '    "함수 호출": "create_safe_operator_call",\n',
        'tag registry')
    _validate_registry(s)
    return s


def patch_plan(s: str) -> str:
    marker = '# CAPSTONE_BATCH19_METRIC_GATE_V1'
    if marker in s:
        return s
    gates = '''    # CAPSTONE_BATCH19_METRIC_GATE_V1: require saved and target evidence.
    # Unobserved or ambiguous styles never create calls or comparisons.
    saved_b19 = _get_style_metrics(diff)
    target_b19 = _get_target_metrics(diff)
    for tag_b19, desired_b19, evidence_b19, action_b19 in (
        ("비교 연산", "compare_count", ("call_count", "import_count"),
         "create_safe_operator_comparison"),
        ("함수 호출", "call_count", ("bin_op_count", "import_count"),
         "create_safe_operator_call"),
    ):
        if (_metric_count(saved_b19, desired_b19) > 0
                and _metric_count(target_b19, desired_b19) == 0
                and all(_metric_count(target_b19, key) > 0 for key in evidence_b19)
                and not any(item.get("action") == action_b19 for item in actions)):
            actions.append({
                "tag": tag_b19,
                "action": action_b19,
                "reason": "저장 스타일의 기존 메트릭과 대상 operator 구문을 확인한 안전 패턴만 변환합니다.",
            })

'''
    s = _replace_once(s,
        '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n',
        gates+'    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n',
        'style plan metric gate')
    # A missing tag alone is not enough evidence for the two new actions.
    s = _replace_once(s,
        '        if action is None:\n            compare_only.append(tag_name)\n            continue\n',
        '        if action is None:\n            compare_only.append(tag_name)\n            continue\n'
        '        if tag_name in {"비교 연산", "함수 호출"}:\n'
        '            continue  # Batch 19: metric gate above is required.\n',
        'plan missing-tag guard')
    ast.parse(s)
    return s


def patch_dispatch(s: str) -> str:
    marker = '# CAPSTONE_BATCH19_DISPATCH_IMPORT_V1'
    if marker in s:
        if '"create_safe_operator_comparison": transform_operator_comparison_to_syntax' not in s:
            raise RuntimeError('Dispatcher batch19 partially installed.')
        return s
    s = _replace_once(s, 'def _get_transform_function(action: str):\n',
        '# CAPSTONE_BATCH19_DISPATCH_IMPORT_V1\n'
        'from app.services.improvement.safe_comparison_batch19_service import (\n'
        '    transform_operator_comparison_to_syntax,\n)\n\n'
        'def _get_transform_function(action: str):\n', 'dispatcher import')
    s = _replace_once(s,
        '        "create_safe_arithmetic_expression": transform_operator_call_to_arithmetic,\n',
        '        "create_safe_arithmetic_expression": transform_operator_call_to_arithmetic,\n'
        '        # CAPSTONE_BATCH19_DISPATCH_MAP_V1\n'
        '        "create_safe_operator_comparison": transform_operator_comparison_to_syntax,\n',
        'dispatcher mapping')
    ast.parse(s)
    return s


def patch_legacy_test(s: str) -> str:
    marker = '# CAPSTONE_BATCH19_LEGACY_TEST_V1'
    if marker in s:
        return s
    s = _replace_once(s,
        '        self.assertEqual(len(keys), 78)\n',
        '        # CAPSTONE_BATCH19_LEGACY_TEST_V1: later batches may add unique tags.\n'
        '        self.assertGreaterEqual(len(keys), 78)\n',
        '13th batch registry baseline')
    s = _replace_once(s,
        '        self.assertEqual(len(mapping.COMPARE_ONLY_TAGS), 24)\n',
        '        self.assertEqual(len(mapping.COMPARE_ONLY_TAGS), 102 - len(keys))\n',
        '13th batch remaining count')
    ast.parse(s)
    return s


def patch_ui(s: str) -> str:
    marker = 'CAPSTONE_BATCH19_REMOVE_STRICT_UI_V1'
    if marker in s:
        if 'strictRuntimeValidation' in s or 'setStrictRuntimeValidation' in s:
            raise RuntimeError('Strict UI remains after batch19 marker.')
        return s
    state = (
        '  // CAPSTONE_BATCH16_STRICT_VERIFY_V1: strict verification is opt-in.\n'
        '  const [strictRuntimeValidation, setStrictRuntimeValidation] = useState(false);\n')
    # UI is exactly the Batch 16 block; later batches added stdin separately.
    start_mark = (
        '          {/* CAPSTONE_BATCH16_STRICT_VERIFY_V1: optional rollback of unverified results */}\n')
    end_mark = '          {/* 스타일 적용 버튼 */}'
    if s.count(state) != 1 or s.count(start_mark) != 1 or s.count(end_mark) != 1:
        raise RuntimeError('Expected strict verification UI/state from Batch 16 not found.')
    start = s.index(start_mark)
    end = s.index(end_mark, start)
    span = s[start:end]
    if not (0 < end-start < 2200 and 'checked={strictRuntimeValidation}' in span
            and 'setStrictRuntimeValidation' in span
            and '엄격 실행 검증' in span):
        raise RuntimeError('Strict verification UI span changed; refusing broad deletion.')
    s = s[:start] + '          {/* CAPSTONE_BATCH19_REMOVE_STRICT_UI_V1: optional strict checkbox removed. */}\n' + s[end:]
    s = _replace_once(s, state, '', 'remove strict checkbox state')
    # Batch 18 retains both forms, Batch 17 may still be locally installed.
    if s.count('void handleApplyStyle(undefined, strictRuntimeValidation') != 1:
        raise RuntimeError('Default apply button call changed; refusing partial update.')
    if s.count('void handleApplyStyle(cases, strictRuntimeValidation') != 1:
        raise RuntimeError('Function-test apply button call changed; refusing partial update.')
    s = s.replace('void handleApplyStyle(undefined, strictRuntimeValidation',
                  'void handleApplyStyle(undefined, false', 1)
    s = s.replace('void handleApplyStyle(cases, strictRuntimeValidation',
                  'void handleApplyStyle(cases, false', 1)
    # CAPSTONE_BATCH19_UI_TYPE_FIX_V2: Batch 17 also added a positional
    # optional strict flag to the callback type. The checkbox removal must
    # update that annotation without changing the hook/API call contract.
    s = _replace_once(s,
        '    strictRuntimeValidation?: boolean,\n    stdin?: string\n',
        '    legacyVerificationOption?: boolean,\n    stdin?: string\n',
        'remove leftover strict callback parameter name')
    if 'strictRuntimeValidation' in s or 'setStrictRuntimeValidation' in s:
        raise RuntimeError('Strict UI reference remains in frontend component.')
    if 'draft.stdinText' not in s or 'functionCases' not in s:
        # The property/function names are different in earlier code paths.
        if 'value={draft.stdinText}' not in s:
            raise RuntimeError('Per-function stdin field is missing; expected Batch 17.')
    return s


PATCHERS = {
    TARGETS[0]: patch_registry,
    TARGETS[1]: patch_plan,
    TARGETS[2]: patch_dispatch,
    TARGETS[3]: patch_legacy_test,
    TARGETS[4]: patch_ui,
}


def _read(path: Path) -> tuple[str, str, bool]:
    data = path.read_bytes()
    bom = data.startswith(b'\xef\xbb\xbf')
    s = data.decode('utf-8-sig')
    if '\r\n' in s and '\n' in s.replace('\r\n', ''):
        raise RuntimeError(f'Mixed CRLF and LF in {path}')
    eol = '\r\n' if '\r\n' in s else '\n'
    return s.replace('\r\n', '\n'), eol, bom


def _encode(source: str, eol: str, bom: bool) -> bytes:
    return (b'\xef\xbb\xbf' if bom else b'') + source.replace('\n', eol).encode('utf-8')


def prepare(root: Path) -> dict[Path, bytes]:
    changes: dict[Path, bytes] = {}
    results: list[bool] = []
    for relative, fn in PATCHERS.items():
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f'Missing expected project file: {relative}')
        old, eol, bom = _read(path)
        new = fn(old)
        results.append(new != old)
        if new != old:
            changes[relative] = _encode(new, eol, bom)
    for relative, payload in NEW.items():
        payload_path = root / payload
        if not payload_path.is_file():
            raise RuntimeError(f'Missing ZIP payload: {payload}')
        contents = payload_path.read_bytes()
        if not contents.endswith(b'\n') or b'\r' in contents:
            raise RuntimeError(f'Invalid payload formatting: {payload}')
        compile(contents, str(relative), 'exec')
        target = root / relative
        if target.exists():
            if target.read_bytes() != contents:
                raise RuntimeError(f'New file exists with other contents: {relative}')
            results.append(False)
        else:
            changes[relative] = contents
            results.append(True)
    if any(results) and not all(results):
        raise RuntimeError('Partial Batch19 installation or conflicting files. Nothing was modified.')
    return changes


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.capstone_batch19_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def install(root: Path, check: bool) -> str:
    if not (root / '.git').is_dir():
        raise RuntimeError('Project .git directory not found.')
    changes = prepare(root)
    if not changes:
        return 'Batch 19 already installed; no changes required.'
    if check:
        return f'Batch19 preflight passed: {len(changes)} files; no changes written.'
    backups = root / '.git' / 'capstone_batch19_backups'
    originals = {name: (root / name).read_bytes() if (root / name).is_file() else None
                 for name in changes}
    for name, original in originals.items():
        if original is None:
            continue
        backup = backups / name
        if backup.exists() and backup.read_bytes() != original:
            raise RuntimeError(f'Conflicting backup: {name}')
    for name, original in originals.items():
        if original is None:
            continue
        backup = backups / name
        if not backup.exists():
            _atomic_write(backup, original)
    completed = []
    try:
        for name, payload in changes.items():
            _atomic_write(root / name, payload)
            completed.append(name)
    except Exception:
        for name in reversed(completed):
            if originals[name] is None:
                (root / name).unlink(missing_ok=True)
            else:
                _atomic_write(root / name, originals[name])
        raise
    return f'Installed Batch 19: {len(changes)} files; operator call & comparison links, strict UI removed.'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(install(ROOT, check=args.check))
    except (RuntimeError, OSError, UnicodeError, ValueError, SyntaxError) as exc:
        print(f'Batch19 installation stopped: {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
