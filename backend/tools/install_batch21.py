"""Install Batch 21 patches onto clean GitHub commit a823395.

From the capstone_main repository root:
  python backend/tools/install_batch21.py --check
  python backend/tools/install_batch21.py

All existing-file preflights run before any write. Original files are backed
up beneath .git/capstone_batch21_backups. Reinstallation is idempotent.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = Path('backend/tools/batch21_payload')
ORIGINALS = {
    Path('backend/app/services/style_tag_transform_map_service.py'): '0d6ae7e371f0409dba930a4bff50f3bedf760f42',
    Path('backend/app/services/style_transform_plan_service.py'): 'fe756495971b87e37254e28ee3b6957cbe1d612c',
    Path('backend/app/services/style_apply_service.py'): '5941396ee0a9eaec08b270d9f224e301f06c43b4',
    Path('backend/tests/test_style_batch20_new_links.py'): 'e6243a2aa42eaeb33ca7aef17b928c4793e31abb',
}
NEW_FILES = {
    Path('backend/app/services/improvement/safe_batch21_service.py'): PAYLOAD / 'safe_batch21_service.py.source',
    Path('backend/tests/test_style_batch21_new_links.py'): PAYLOAD / 'test_style_batch21_new_links.py.source',
    Path('backend/tools/audit_transform_batch21.py'): PAYLOAD / 'audit_transform_batch21.py.source',
}
MARK = 'CAPSTONE_BATCH21_'


def _replace_once(source: str, before: str, after: str, label: str) -> str:
    if source.count(before) != 1:
        raise RuntimeError(f'{label}: unexpected source shape ({source.count(before)} matches)')
    return source.replace(before, after, 1)


def _registry_keys(source: str) -> list[str]:
    tree = ast.parse(source)
    dicts = [node.value for node in tree.body
             if isinstance(node, ast.AnnAssign)
             and isinstance(node.target, ast.Name)
             and node.target.id == 'CREATE_ACTION_BY_TAG'
             and isinstance(node.value, ast.Dict)]
    if len(dicts) != 1:
        raise RuntimeError('No unique tag dictionary found')
    return [key.value for key in dicts[0].keys if isinstance(key, ast.Constant)]


def patch_registry(source: str) -> str:
    if MARK in source:
        raise RuntimeError('Partial Batch21 registry marker detected')
    before = _registry_keys(source)
    if len(before) != 82 or len(before) != len(set(before)):
        raise RuntimeError('Expected exactly 82 distinct Batch20 registry keys')
    if any(t in before for t in ('input 사용', 'assert문')):
        raise RuntimeError('Batch21 tags already in an unmarked registry')
    source = _replace_once(source,
        'CREATE_ACTION_BY_TAG: dict[str, str] = {\n',
        'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
        '    # CAPSTONE_BATCH21_REGISTRY_V1: narrow input and assertion styles.\n'
        '    "input 사용": "create_safe_builtin_input",\n'
        '    "assert문": "create_safe_debug_assert",\n', 'registry')
    keys = _registry_keys(source)
    if len(keys) != 84 or len(keys) != len(set(keys)):
        raise RuntimeError('Invalid Batch21 registry result')
    return source


def patch_plan(source: str) -> str:
    if MARK in source:
        raise RuntimeError('Partial Batch21 plan marker detected')
    addition = '''    # CAPSTONE_BATCH21_METRIC_GATE_V1: only recorded preferences select actions.
    # Assert changes require an explicit __debug__ guard. Input only rewrites a
    # prior-imported builtins.input call without changing the prompt or stdin.
    saved_b21 = _get_style_metrics(diff)
    target_b21 = _get_target_metrics(diff)
    for tag_b21, saved_metric, evidence, action_b21 in (
        ("input 사용", "input_call_count", ("import_count", "attribute_count", "call_count"),
         "create_safe_builtin_input"),
        ("assert문", "assert_count", ("if_count", "raise_count"),
         "create_safe_debug_assert"),
    ):
        if (_metric_count(saved_b21, saved_metric) > 0
                and _metric_count(target_b21, saved_metric) == 0
                and all(_metric_count(target_b21, metric) > 0 for metric in evidence)
                and not any(item.get("action") == action_b21 for item in actions)):
            actions.append({
                "tag": tag_b21,
                "action": action_b21,
                "reason": "저장된 메트릭과 국소 코드 패턴에 근거한 안전한 변환만 실행합니다.",
            })

'''
    source = _replace_once(source,
        '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n',
        addition + '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n', 'plan metric gate')
    source = _replace_once(source,
        '        # CAPSTONE_BATCH20_METRIC_ONLY_V1: missing-tag evidence alone is insufficient.\n',
        '        # CAPSTONE_BATCH21_METRIC_ONLY_V1: unobserved tag name is not enough.\n'
        '        if tag_name in {"input 사용", "assert문"}:\n'
        '            continue\n'
        '        # CAPSTONE_BATCH20_METRIC_ONLY_V1: missing-tag evidence alone is insufficient.\n',
        'plan missing-tag guard')
    ast.parse(source)
    return source


def patch_dispatch(source: str) -> str:
    if MARK in source:
        raise RuntimeError('Partial Batch21 dispatcher marker detected')
    source = _replace_once(source,
        'def _get_transform_function(action: str):\n',
        '# CAPSTONE_BATCH21_DISPATCH_IMPORT_V1\n'
        'from app.services.improvement.safe_batch21_service import (\n'
        '    transform_safe_builtin_input, transform_debug_guard_to_assert,\n'
        ')\n\n'
        'def _get_transform_function(action: str):\n', 'dispatcher import')
    source = _replace_once(source,
        '    action_map = {\n',
        '    action_map = {\n'
        '        # CAPSTONE_BATCH21_DISPATCH_MAP_V1\n'
        '        "create_safe_builtin_input": transform_safe_builtin_input,\n'
        '        "create_safe_debug_assert": transform_debug_guard_to_assert,\n',
        'dispatcher action map')
    ast.parse(source)
    return source


def patch_old_tests(source: str) -> str:
    if MARK in source:
        raise RuntimeError('Partial Batch21 compatibility-test marker detected')
    source = _replace_once(source,
        '        self.assertEqual(len(CREATE_ACTION_BY_TAG), 82)\n'
        '        self.assertEqual(len(COMPARE_ONLY_TAGS), 20)\n',
        '        # CAPSTONE_BATCH21_LEGACY_BASELINE_V1: later batches may extend the registry.\n'
        '        self.assertGreaterEqual(len(CREATE_ACTION_BY_TAG), 82)\n'
        '        self.assertLessEqual(len(COMPARE_ONLY_TAGS), 20)\n'
        '        self.assertEqual(len(CREATE_ACTION_BY_TAG) + len(COMPARE_ONLY_TAGS), 102)\n',
        'batch20 legacy count assertions')
    ast.parse(source)
    return source


def _blob_sha(blob: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(blob)).encode() + b'\0' + blob).hexdigest()


def _read_source(path: Path):
    raw = path.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    contents = raw[3:] if bom else raw
    eol = '\r\n' if b'\r\n' in contents else '\n'
    if b'\r\n' in contents and contents.replace(b'\r\n', b'').find(b'\n') >= 0:
        raise RuntimeError(f'Mixed line endings: {path}')
    normalized = contents.replace(b'\r\n', b'\n')
    return normalized.decode('utf-8'), eol, bom, raw, normalized


def _encoded(text: str, eol: str, bom: bool):
    return (b'\xef\xbb\xbf' if bom else b'') + text.replace('\n', eol).encode('utf-8')


def prepare(root: Path, *, enforce_sha=True):
    if not (root / '.git').is_dir():
        raise RuntimeError('Run from Git working tree capstone_main (missing .git).')
    staged: dict[Path, bytes] = {}
    originals = {}
    applied_flags = []
    operations = {
        Path('backend/app/services/style_tag_transform_map_service.py'): patch_registry,
        Path('backend/app/services/style_transform_plan_service.py'): patch_plan,
        Path('backend/app/services/style_apply_service.py'): patch_dispatch,
        Path('backend/tests/test_style_batch20_new_links.py'): patch_old_tests,
    }
    for rel, patch in operations.items():
        path = root / rel
        if not path.is_file():
            raise RuntimeError(f'Missing required file: {rel}')
        source, eol, bom, raw, normalized = _read_source(path)
        installed = MARK in source
        applied_flags.append(installed)
        if not installed:
            if enforce_sha and _blob_sha(normalized) != ORIGINALS[rel]:
                raise RuntimeError(f'Changed base file since a823395: {rel}. '
                                   'Do not overwrite unrelated work; commit or reconcile first.')
            updated = patch(source)
            staged[rel] = _encoded(updated, eol, bom)
            originals[rel] = raw
        else:
            # Compare marker presence rather than assuming a partial install.
            if rel.name == 'style_tag_transform_map_service.py' and len(_registry_keys(source)) != 84:
                raise RuntimeError('Partial installed registry')
    new_flags = []
    for rel, payload_rel in NEW_FILES.items():
        path = root / rel
        payload_file = root / payload_rel
        if not payload_file.is_file():
            raise RuntimeError(f'Payload missing: {payload_rel}')
        payload = payload_file.read_bytes()
        ast.parse(payload.decode('utf-8'))
        exists = path.exists()
        new_flags.append(exists)
        if exists:
            if path.read_bytes() != payload:
                raise RuntimeError(f'Existing new file differs: {rel}')
        else:
            staged[rel] = payload
    if (any(applied_flags) or any(new_flags)) and not (all(applied_flags) and all(new_flags)):
        raise RuntimeError('Partial Batch21 install detected. No files changed.')
    return staged, originals


def _atomic_write(target: Path, payload: bytes):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.capstone_b21_', suffix='.tmp', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(payload)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(root: Path, *, check=False, enforce_sha=True):
    staged, originals = prepare(root, enforce_sha=enforce_sha)
    if not staged:
        return 'Batch21 already installed; no files changed.'
    if check:
        return f'Batch21 preflight passed: {len(staged)} files ready; no changes made.'
    backup = root / '.git' / 'capstone_batch21_backups'
    backup.mkdir(parents=True, exist_ok=True)
    for rel, data in originals.items():
        dest = backup / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.read_bytes() != data:
            raise RuntimeError(f'Conflicting previous backup: {dest}')
        if not dest.exists():
            _atomic_write(dest, data)
    completed = []
    try:
        for rel, data in staged.items():
            target = root / rel
            _atomic_write(target, data)
            completed.append(rel)
    except Exception:
        for rel in reversed(completed):
            target = root / rel
            if rel in originals:
                _atomic_write(target, originals[rel])
            else:
                target.unlink(missing_ok=True)
        raise
    return f'Installed Batch21: {len(staged)} files; input/assert safe actions.'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(install(ROOT, check=args.check))
        return 0
    except (RuntimeError, UnicodeError, OSError, SyntaxError, ValueError) as exc:
        print(f'Batch21 installation stopped: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
