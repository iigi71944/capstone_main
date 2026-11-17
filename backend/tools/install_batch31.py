"""Install Batch31's seven constrained tag links on top of the Batch30 hotfix.

Usage (Windows project root):
    python backend\\tools\\install_batch31.py --check
    python backend\\tools\\install_batch31.py

Checks all anchors and payload hashes before writing; stores original bytes in
.git/capstone_batch31_backup and atomically replaces files with rollback.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = ROOT / 'backend' / 'tools' / 'batch31_payload'
MARK = 'CAPSTONE_BATCH31_LINK_ALL_V1'

REGISTRY = Path('backend/app/services/style_tag_transform_map_service.py')
PLAN = Path('backend/app/services/style_transform_plan_service.py')
APPLY = Path('backend/app/services/style_apply_service.py')
AUDIT30 = Path('backend/tools/audit_transform_batch30.py')
LEGACY = {
    Path('backend/tests/test_style_batch27_new_links.py'): 'batch27',
    Path('backend/tests/test_style_batch28_tag_policies.py'): 'batch28',
    Path('backend/tests/test_style_batch30_policy_conflicts.py'): 'batch30',
    Path('backend/tests/test_style_batch24_new_links.py'): 'batch24',
    Path('backend/tests/test_style_unmapped_patterns_batch10_integration.py'): 'batch10',
    Path('backend/tests/test_style_unmapped_patterns_batch11_integration.py'): 'batch11',
    Path('backend/tests/test_style_unmapped_patterns_batch12_integration.py'): 'batch12',
    Path('backend/tests/test_style_unmapped_patterns_batch13_integration.py'): 'batch13',
}
NEW = {
    Path('backend/app/services/improvement/safe_batch31_service.py'): 'safe_batch31_service.py.source',
    Path('backend/tests/test_style_batch31_new_links.py'): 'test_style_batch31_new_links.py.source',
    Path('backend/tools/audit_transform_batch31.py'): 'audit_transform_batch31.py.source',
}


def _once(text: str, before: str, after: str, name: str) -> str:
    n = text.count(before)
    if n != 1:
        raise RuntimeError(f'{name}: expected one anchor, found {n}. Nothing changed.')
    return text.replace(before, after, 1)


def _read(path: Path):
    raw = path.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    body = raw[3:] if bom else raw
    if b'\n' in body.replace(b'\r\n', b'') and b'\r\n' in body:
        raise RuntimeError(f'{path}: mixed newline styles are not supported')
    if b'\r' in body.replace(b'\r\n', b''):
        raise RuntimeError(f'{path}: stray CR newline is not supported')
    eol = '\r\n' if b'\r\n' in body else '\n'
    return body.replace(b'\r\n', b'\n').decode('utf-8'), raw, eol, bom


def _encode(src, eol, bom):
    return (b'\xef\xbb\xbf' if bom else b'') + src.replace('\n', eol).encode('utf-8')


def _write_atomic(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.batch31_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def patch_registry(src: str) -> str:
    anchor = 'CREATE_ACTION_BY_TAG: dict[str, str] = {\n'
    add = '''    # CAPSTONE_BATCH31_LINK_ALL_V1: only narrow closed-module safe styles.
    "기본 매개변수": "create_safe_closed_default_parameter",
    "가변 인자 사용": "create_safe_closed_varargs",
    "키워드 가변 인자 사용": "create_safe_closed_kwargs",
    "비동기 함수 정의": "create_safe_closed_async_definition",
    "await 사용": "create_safe_closed_await",
    "비동기 처리 구조": "create_safe_closed_async_structure",
    "긴 함수 구조": "create_safe_closed_long_function",
'''
    src = _once(src, anchor, anchor + add, '31 registry')
    tree = ast.parse(src)
    assign = next(n for n in tree.body if isinstance(n, ast.AnnAssign)
                  and isinstance(n.target, ast.Name) and n.target.id == 'CREATE_ACTION_BY_TAG')
    keys = [k.value for k in assign.value.keys]
    if len(keys) != 102 or len(set(keys)) != 102:
        raise RuntimeError('31 registry must contain exactly 102 unique tags')
    return src


def patch_plan(src: str) -> str:
    if 'CAPSTONE_BATCH30_DEFAULT_ARG_GATE_FIX_V1' not in src:
        raise RuntimeError('Missing the final Batch30 fine-metric-overlap fix')
    if 'CAPSTONE_BATCH29_FINE_PLAN_V1' not in src or 'CAPSTONE_BATCH28_PLAN_FINALIZE_V1' not in src:
        raise RuntimeError('Batch28/29 plan metadata is missing')
    anchor = '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n'
    body = '''    # CAPSTONE_BATCH31_METRIC_GATES_V1: each newly linked tag must have
    # observed saved-style metrics and a conservatively matching target shape.
    # The transformer itself verifies every AST node before any source edit.
    saved_b31 = _get_style_metrics(diff)
    target_b31 = _get_target_metrics(diff)
    concepts_b31 = _get_tag_names(diff, "style_concept_names")

    for tag_b31, saved_metric, target_metric, action_b31 in (
        ("기본 매개변수", "default_param_count", "default_param_count", "create_safe_closed_default_parameter"),
        ("가변 인자 사용", "vararg_count", "vararg_count", "create_safe_closed_varargs"),
        ("키워드 가변 인자 사용", "kwarg_count", "kwarg_count", "create_safe_closed_kwargs"),
    ):
        if (_metric_count(saved_b31, saved_metric) > 0
                and _metric_count(target_b31, target_metric) == 0
                and _metric_count(target_b31, "function_count") == 1
                and _metric_count(target_b31, "call_count") > 0):
            actions.append({
                "tag": tag_b31, "action": action_b31,
                "reason": "저장 스타일의 매개변수 선호가 관측된 단독 내부 함수에만 안전한 시그니처 변환을 시도합니다.",
            })

    if (_metric_count(saved_b31, "async_function_count") > 0
            and _metric_count(target_b31, "async_function_count") == 0
            and _metric_count(target_b31, "function_count") == 1
            and _metric_count(target_b31, "import_count") == 1
            and _metric_count(target_b31, "call_count") >= 2):
        actions.append({
            "tag": "비동기 함수 정의", "action": "create_safe_closed_async_definition",
            "reason": "고립된 리터럴 반환 내부 함수를 asyncio.run 호출과 함께 비동기로 구성합니다.",
        })

    prefer_async_structure_b31 = (
        "비동기 처리 구조" in concepts_b31
        and _metric_count(saved_b31, "async_function_count") >= 2
        and _metric_count(saved_b31, "await_count") > 0
        and _metric_count(target_b31, "async_function_count") == 1
        and _metric_count(target_b31, "await_count") == 0
        and _metric_count(target_b31, "import_count") == 1
    )
    if prefer_async_structure_b31:
        actions.append({
            "tag": "비동기 처리 구조", "action": "create_safe_closed_async_structure",
            "reason": "독립 asyncio 스크립트에 작은 await 실행 함수를 도입합니다.",
        })
    elif (_metric_count(saved_b31, "await_count") > 0
            and _metric_count(target_b31, "await_count") == 0
            and _metric_count(target_b31, "async_function_count") == 1
            and _metric_count(target_b31, "import_count") == 1):
        actions.append({
            "tag": "await 사용", "action": "create_safe_closed_await",
            "reason": "고립된 상수 반환 코루틴에 결과 동일성이 검증된 await 표현을 적용합니다.",
        })

    if ("긴 함수 구조" in concepts_b31
            and _metric_count(saved_b31, "max_function_body_length") >= 10
            and _metric_count(target_b31, "max_function_body_length") < 10
            and _metric_count(target_b31, "function_count") == 1
            and _metric_count(target_b31, "loop_count") > 0):
        actions.append({
            "tag": "긴 함수 구조", "action": "create_safe_closed_long_function",
            "reason": "출력만 수행하는 고정 리터럴 반복문을 여러 명시적 문장으로 펼칩니다.",
        })

'''
    src = _once(src, anchor, body + anchor, '31 metric-gated planner')
    anchor = '        if action is None:\n            compare_only.append(tag_name)\n            continue\n'
    deny = '''        # CAPSTONE_BATCH31_METRIC_ONLY_V1: tag labels alone cannot rewrite APIs.
        if tag_name in {
            "기본 매개변수", "가변 인자 사용", "키워드 가변 인자 사용",
            "비동기 함수 정의", "await 사용", "비동기 처리 구조", "긴 함수 구조",
        }:
            continue
'''
    return _once(src, anchor, anchor + deny, '31 label-only gate')


def patch_apply(src: str) -> str:
    anchor = 'def _get_transform_function(action: str):\n'
    add = '''# CAPSTONE_BATCH31_DISPATCH_IMPORT_V1
from app.services.improvement.safe_batch31_service import TRANSFORMERS as BATCH31_TRANSFORMERS

'''
    src = _once(src, anchor, add + anchor, '31 dispatcher import')
    anchor = '    action_map = {\n'
    src = _once(src, anchor, anchor + '        # CAPSTONE_BATCH31_DISPATCH_MAP_V1\n', '31 dispatcher anchor')
    anchor = '    return action_map.get(action)\n'
    return _once(src, anchor, '    return action_map.get(action) or BATCH31_TRANSFORMERS.get(action)\n',
                 '31 dispatcher fallback')


def patch_legacy(src: str, case: str) -> str:
    if case == 'batch27':
        src = _once(src, '        self.assertEqual(len(CREATE_ACTION_BY_TAG), 95)\n        self.assertEqual(len(COMPARE_ONLY_TAGS), 7)\n',
                    '        # Batch31 extends the earlier minimum without changing old mappings.\n'
                    '        self.assertGreaterEqual(len(CREATE_ACTION_BY_TAG), 95)\n'
                    '        self.assertLessEqual(len(COMPARE_ONLY_TAGS), 7)\n'
                    '        self.assertEqual(len(CREATE_ACTION_BY_TAG) + len(COMPARE_ONLY_TAGS), 102)\n', case)
    elif case == 'batch28':
        src = _once(src, '        self.assertEqual(len(CREATE_ACTION_BY_TAG), 95)\n        self.assertEqual(len(COMPARE_ONLY_TAGS), 7)\n',
                    '        self.assertGreaterEqual(len(CREATE_ACTION_BY_TAG), 95)\n'
                    '        self.assertLessEqual(len(COMPARE_ONLY_TAGS), 7)\n'
                    '        self.assertEqual(len(CREATE_ACTION_BY_TAG) + len(COMPARE_ONLY_TAGS), 102)\n', case)
    elif case == 'batch30':
        src = _once(src, "        self.assertEqual((len(CREATE_ACTION_BY_TAG), len(COMPARE_ONLY_TAGS)), (95, 7))\n",
                    "        self.assertEqual((len(CREATE_ACTION_BY_TAG), len(COMPARE_ONLY_TAGS)), (102, 0))\n", case)
    elif case == 'batch24':
        src = _once(src,
                    "        for tag in ('await 사용', '기본 매개변수'):\n"
                    "            self.assertNotIn(tag, CREATE_ACTION_BY_TAG)\n"
                    "            self.assertIn(tag, COMPARE_ONLY_TAGS)\n",
                    "        # Batch31: formerly risky tags now have guarded closed-module transforms.\n"
                    "        for tag in ('await 사용', '기본 매개변수'):\n"
                    "            self.assertIn(tag, CREATE_ACTION_BY_TAG)\n"
                    "            self.assertNotIn(tag, COMPARE_ONLY_TAGS)\n", case)
    elif case in ('batch10', 'batch11'):
        src = _once(src,
                    "self.assertEqual(get_tag_transform_status('await 사용'), 'compare_only')",
                    "self.assertEqual(get_tag_transform_status('await 사용'), 'linked')", case)
    elif case == 'batch12':
        src = _once(src, "self.assertEqual(get_tag_transform_status(tag), 'compare_only')",
                    "self.assertEqual(get_tag_transform_status(tag), 'linked')", case)
    elif case == 'batch13':
        src = _once(src, "self.assertEqual(mapping.get_tag_transform_status(tag), 'compare_only')",
                    "self.assertEqual(mapping.get_tag_transform_status(tag), 'linked')", case)
    return src


def patch_audit30(src: str) -> str:
    src = _once(src,
        '    if len(CREATE_ACTION_BY_TAG) != 95 or len(COMPARE_ONLY_TAGS) != 7:\n',
        '    if (len(CREATE_ACTION_BY_TAG) < 95 or len(COMPARE_ONLY_TAGS) > 7\n'
        '            or len(CREATE_ACTION_BY_TAG) + len(COMPARE_ONLY_TAGS) != 102):\n',
        '31 old audit count gate')
    src = _once(src,
        "        and s['tags'] == 102 and s['linked'] == 95 and s['compare_only'] == 7\n",
        "        and s['tags'] == 102 and s['linked'] >= 95 and s['compare_only'] <= 7\n",
        '31 audit main count gate')
    return src


def preflight(root: Path):
    if not (root / '.git').is_dir():
        raise RuntimeError('Run from capstone_main Git repository root')
    targets = {REGISTRY: patch_registry, PLAN: patch_plan, APPLY: patch_apply,
               AUDIT30: patch_audit30}
    originals = {}
    updated = {}
    for rel, patcher in targets.items():
        p = root / rel
        if not p.is_file():
            raise RuntimeError(f'Missing required source {rel}')
        src, raw, eol, bom = _read(p)
        originals[rel] = raw
        if MARK in src or 'CAPSTONE_BATCH31_METRIC_GATES_V1' in src:
            raise RuntimeError('Batch31 appears partially/already installed; no files changed')
        changed = patcher(src)
        ast.parse(changed)
        updated[rel] = _encode(changed, eol, bom)
    if 'CAPSTONE_BATCH27_REGISTRY_V1' not in _read(root / REGISTRY)[0]:
        raise RuntimeError('Batch27 registry baseline missing')
    if 'CAPSTONE_BATCH29_DISPATCH_MAP_V1' not in _read(root / APPLY)[0]:
        raise RuntimeError('Batch29 dispatcher baseline missing')

    for rel, case in LEGACY.items():
        p = root / rel
        if not p.is_file():
            raise RuntimeError(f'Missing legacy test {rel}')
        src, raw, eol, bom = _read(p)
        originals[rel] = raw
        changed = patch_legacy(src, case)
        ast.parse(changed)
        updated[rel] = _encode(changed, eol, bom)

    for rel, filename in NEW.items():
        dest = root / rel
        if dest.exists():
            raise RuntimeError(f'New Batch31 file already exists: {rel}')
        source = PAYLOAD / filename
        if not source.is_file():
            raise RuntimeError(f'Missing payload {source}')
        data = source.read_bytes()
        expected = PAYLOAD_SHA256[filename]
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError(f'Payload hash mismatch: {filename}')
        ast.parse(data.decode('utf-8'))
        updated[rel] = data
    return originals, updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Validate, do not change files')
    args = parser.parse_args()
    try:
        originals, updates = preflight(ROOT)
        if args.check:
            print(f'Batch31 preflight OK: {len(updates)} files, 7 new tags, 21 real triplets; no changes')
            return 0
        backup = ROOT / '.git' / 'capstone_batch31_backup'
        for rel, raw in originals.items():
            target = backup / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if target.read_bytes() != raw:
                    raise RuntimeError(f'Conflicting backup exists: {target}')
            else:
                _write_atomic(target, raw)
        written = []
        try:
            for rel, data in updates.items():
                _write_atomic(ROOT / rel, data)
                written.append(rel)
        except Exception:
            for rel in reversed(written):
                if rel in originals:
                    _write_atomic(ROOT / rel, originals[rel])
                else:
                    (ROOT / rel).unlink(missing_ok=True)
            raise
        print(f'Batch31 installed: 7 guarded transformers; {len(written)} files. Frontend unchanged.')
        print('Run all backend unittest tests, then tools/audit_transform_batch31.py.')
        return 0
    except (OSError, RuntimeError, UnicodeError, SyntaxError, ValueError) as error:
        print(f'Batch31 installation stopped safely: {error}')
        return 1


# Filled during package assembly; the installer rejects tampered payloads.
PAYLOAD_SHA256 = {'safe_batch31_service.py.source': 'c5396f2fa4051499410de3eb3e9efbd24bc48d1ca4f4edd0da6eb98cd524913d', 'audit_transform_batch31.py.source': 'a2b2f643c4990cd7ad0979db224b3c9ca30f577efe92661d467a25333faaa78f', 'test_style_batch31_new_links.py.source': '722841d1ea50a72bf7113c39b1b3f0dc5ee6569073f692224c556c40007f8009'}

if __name__ == '__main__':
    raise SystemExit(main())
