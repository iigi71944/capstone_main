"""29차 세부 코딩 스타일 메트릭/변환 패치 설치 도구.

반드시 28차 및 출처 보존 수정이 설치된 capstone_main 루트에서 실행:
    python backend/tools/install_batch29.py --check
    python backend/tools/install_batch29.py

백엔드만 수정하며 프론트엔드 파일/태그 목록/저장 포맷은 변경하지 않습니다.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = Path('backend/tools/batch29_payload')
BASE = {
    Path('backend/app/services/metric_service.py'): 'c0c1f3b241eea86123ffa567ea956aeb36a9b2b0',
    Path('backend/app/services/style_transform_plan_service.py'): 'a702986820aa9e75d376195a2f5889c037b2dedb',
    Path('backend/app/services/style_apply_service.py'): '9d69ef9cced412e4afa8e9ac2d35abe21f367446',
    Path('backend/app/services/style_tag_action_policy_service.py'): '746ee2e1cbe018818ebd389037bd5d371d30bf60',
}
REGISTRY_SHA = 'ae4a4c9126738ff91c688e50e41dbc9f64bcdb3c'
NEW = {
    Path('backend/app/services/style_fine_pattern_metric_service.py'):
        PAYLOAD / 'style_fine_pattern_metric_service.py.source',
    Path('backend/app/services/improvement/safe_batch29_service.py'):
        PAYLOAD / 'safe_batch29_service.py.source',
    Path('backend/tests/test_style_batch29_fine_patterns.py'):
        PAYLOAD / 'test_style_batch29_fine_patterns.py.source',
    Path('backend/tools/audit_transform_batch29.py'):
        PAYLOAD / 'audit_transform_batch29.py.source',
}
MARK = 'CAPSTONE_BATCH29_'
PAYLOAD_SHA256 = {
    'backend/tools/batch29_payload/audit_transform_batch29.py.source': '74503e6f2d2eb029ed10b8c139f77736d848dc9eb0d275c1639326f20801498a',
    'backend/tools/batch29_payload/style_fine_pattern_metric_service.py.source': '350f30daa05d56f332508c5f2ed409ba3d59c56f7ff37156684321348b89ab81',
    'backend/tools/batch29_payload/test_style_batch29_fine_patterns.py.source': 'd39b4ebf989e60aa0f0e4be6579136816cafe1d166f82cff9ef0467e3345ec1a',
    'backend/tools/batch29_payload/safe_batch29_service.py.source': 'ebdd292442188f934ec39ec893432bba0ccbb0aed01759ec2c499aabfa771b35',
}



def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def once(src, before, after, label):
    count = src.count(before)
    if count != 1:
        raise RuntimeError(f'{label}: source anchor mismatch ({count})')
    return src.replace(before, after, 1)


def patch_metrics(src):
    anchor = 'from app.services.syntax_tag_service import (\n'
    src = once(src, anchor,
        'from app.services.style_fine_pattern_metric_service import calculate_fine_pattern_metrics\n'
        '# CAPSTONE_BATCH29_METRICS_IMPORT_V1\n' + anchor,
        'metric import')
    anchor = '    selection_visitor.visit(tree)\n\n    return {\n'
    src = once(src, anchor,
        '    selection_visitor.visit(tree)\n\n'
        '    # CAPSTONE_BATCH29_FINE_METRICS_V1: append detail keys, preserve all old keys.\n'
        '    return {\n'
        '        **calculate_fine_pattern_metrics(tree, receiver_types),\n',
        'metric return')
    return src


def patch_plan(src):
    base = 'from app.services.style_tag_action_policy_service import finalize_tag_action_policies\n'
    if base not in src:
        raise RuntimeError('Batch28 policy plan is not installed')
    anchor = '    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:\n'
    addition = '''    # CAPSTONE_BATCH29_FINE_PLAN_V1: only explicit style-metric evidence;
    # no unobserved tag or legacy style can activate these variants.
    saved_b29 = _get_style_metrics(diff)
    target_b29 = _get_target_metrics(diff)
    for tag_b29, saved_key, opposite_key, target_key, action_b29, family_key in (
        ("sorted 사용", "sorted_reverse_false_explicit_count",
         "sorted_reverse_false_implicit_count", "sorted_reverse_false_implicit_count",
         "create_safe_explicit_sorted_reverse", "sorted_call_count"),
        ("sorted 사용", "sorted_reverse_false_implicit_count",
         "sorted_reverse_false_explicit_count", "sorted_reverse_false_explicit_count",
         "create_safe_implicit_sorted_reverse", "sorted_call_count"),
        ("문자열 메서드 호출", "strip_none_explicit_count",
         "strip_none_implicit_count", "strip_none_implicit_count",
         "create_safe_explicit_strip_default", "string_strip_call_count"),
        ("문자열 메서드 호출", "strip_none_implicit_count",
         "strip_none_explicit_count", "strip_none_explicit_count",
         "create_safe_implicit_strip_default", "string_strip_call_count"),
    ):
        if (_metric_count(saved_b29, saved_key) > 0
                and _metric_count(saved_b29, opposite_key) == 0
                and _metric_count(target_b29, target_key) > 0
                and _metric_count(target_b29, saved_key) == 0
                and _metric_count(saved_b29, family_key) > 0
                and _metric_count(target_b29, family_key) > 0
                and not any(item.get("action") == action_b29 for item in actions)):
            actions.append({
                "tag": tag_b29,
                "action": action_b29,
                "reason": "저장 스타일의 세부 메트릭으로 확인된 기본 인자 표현만 안전하게 조정합니다.",
            })

'''
    src = once(src, anchor, addition + anchor, 'plan metric gating')
    anchor = '    "assert_raise": {"create_safe_debug_assert", "create_safe_debug_raise"},\n'
    src = once(src, anchor, anchor + '''    # CAPSTONE_BATCH29_SAFE_DIRECTIONS_V1
    "sorted_default": {"create_safe_explicit_sorted_reverse", "create_safe_implicit_sorted_reverse"},
    "strip_default": {"create_safe_explicit_strip_default", "create_safe_implicit_strip_default"},
''', 'plan direction conflicts')
    return src


def patch_apply(src):
    anchor = 'def _get_transform_function(action: str):\n'
    src = once(src, anchor, '''# CAPSTONE_BATCH29_DISPATCH_IMPORT_V1
from app.services.improvement.safe_batch29_service import (
    transform_sorted_explicit_reverse_default,
    transform_sorted_implicit_reverse_default,
    transform_strip_explicit_none_default,
    transform_strip_implicit_none_default,
)

''' + anchor, 'dispatch import')
    anchor = '        # CAPSTONE_BATCH27_DISPATCH_MAP_V1\n'
    src = once(src, anchor, '''        # CAPSTONE_BATCH29_DISPATCH_MAP_V1
        "create_safe_explicit_sorted_reverse": transform_sorted_explicit_reverse_default,
        "create_safe_implicit_sorted_reverse": transform_sorted_implicit_reverse_default,
        "create_safe_explicit_strip_default": transform_strip_explicit_none_default,
        "create_safe_implicit_strip_default": transform_strip_implicit_none_default,
''' + anchor, 'dispatch map')
    return src


def patch_policy(src):
    anchor = '''_SAFE_ACTION_OVERRIDES = {
    "리스트 누적 방식 사용": "create_safe_append_collection",
    "리스트 컴프리헨션": "create_safe_comprehension_collection",
}
'''
    src = once(src, anchor, anchor + '''
# CAPSTONE_BATCH29_POLICY_ALLOWED_V1: finer syntax decisions reuse the old
# shared engine family but select a separately verified safe action.
_BATCH29_ALLOWED_SAFE_ACTIONS = {
    "sorted 사용": frozenset({"create_safe_explicit_sorted_reverse", "create_safe_implicit_sorted_reverse"}),
    "문자열 메서드 호출": frozenset({"create_safe_explicit_strip_default", "create_safe_implicit_strip_default"}),
}
''', 'policy variants')
    anchor = '            allowed = {action}\n'
    src = once(src, anchor, anchor + '            allowed.update(_BATCH29_ALLOWED_SAFE_ACTIONS.get(tag, ()))\n', 'policy accepted actions')
    anchor = '    safe_variant = action in _SAFE_ACTION_OVERRIDES.values()\n'
    src = once(src, anchor,
               '    safe_variant = (action in _SAFE_ACTION_OVERRIDES.values()\n'
               '                    or any(action in actions for actions in _BATCH29_ALLOWED_SAFE_ACTIONS.values()))\n',
               'policy priority')
    return src


PATCHES = {
    Path('backend/app/services/metric_service.py'): patch_metrics,
    Path('backend/app/services/style_transform_plan_service.py'): patch_plan,
    Path('backend/app/services/style_apply_service.py'): patch_apply,
    Path('backend/app/services/style_tag_action_policy_service.py'): patch_policy,
}


def read_file(path):
    raw = path.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    body = raw[3:] if bom else raw
    if b'\r\n' in body and b'\n' in body.replace(b'\r\n', b''):
        raise RuntimeError(f'{path}: mixed line endings')
    if b'\r' in body.replace(b'\r\n', b''):
        raise RuntimeError(f'{path}: unsupported bare CR')
    eol = '\r\n' if b'\r\n' in body else '\n'
    src = body.replace(b'\r\n', b'\n').decode('utf-8')
    return src, eol, bom, raw


def encoded(src, eol, bom):
    return (b'\xef\xbb\xbf' if bom else b'') + src.replace('\n', eol).encode('utf-8')


def preflight(root):
    if not (root / '.git').is_dir():
        raise RuntimeError('capstone_main Git 폴더에서 실행해야 합니다.')
    registry = root / 'backend/app/services/style_tag_transform_map_service.py'
    if not registry.is_file():
        raise RuntimeError('태그 레지스트리가 존재하지 않습니다.')
    registry_source, _, _, _ = read_file(registry)
    if blob(registry_source.encode('utf-8')) != REGISTRY_SHA:
        raise RuntimeError('태그 레지스트리가 27/28차 기준과 다릅니다. 중단합니다.')
    staged = {}
    original = {}
    flags = []
    for rel, patch in PATCHES.items():
        path = root / rel
        if not path.is_file():
            raise RuntimeError(f'필수 파일 없음: {rel}')
        src, eol, bom, raw = read_file(path)
        flag = MARK in src
        flags.append(flag)
        if flag:
            continue
        if blob(src.encode('utf-8')) != BASE[rel]:
            raise RuntimeError(f'원본 버전 불일치: {rel}; 28차 핫픽스 설치 여부 확인')
        out = patch(src)
        ast.parse(out)
        staged[rel] = encoded(out, eol, bom)
        original[rel] = raw
    present = []
    for rel, payload_rel in NEW.items():
        payload = root / payload_rel
        if not payload.is_file():
            raise RuntimeError(f'패치 구성 파일 없음: {payload_rel}')
        contents = payload.read_bytes()
        expected = PAYLOAD_SHA256[payload_rel.as_posix()]
        if hashlib.sha256(contents).hexdigest() != expected:
            raise RuntimeError(f'ZIP 파일 무결성 실패: {payload_rel}')
        ast.parse(contents.decode('utf-8'))
        dst = root / rel
        present.append(dst.exists())
        if dst.exists():
            if not dst.is_file() or dst.read_bytes() != contents:
                raise RuntimeError(f'기존 파일 충돌: {rel}')
        else:
            staged[rel] = contents
    if (any(flags) or any(present)) and not (all(flags) and all(present)):
        raise RuntimeError('부분 설치 상태입니다. 파일을 변경하지 않았습니다.')
    return staged, original


def atomic_write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.capstone_b29_', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def install(root=ROOT, check=False):
    staged, originals = preflight(root)
    if not staged:
        return '29차 패치가 이미 설치되어 있습니다. 변경 없음.'
    if check:
        return f'29차 사전 검사 통과: 파일 {len(staged)}개 준비, 변경 없음.'
    backups = root / '.git/capstone_batch29_backups'
    if backups.exists():
        raise RuntimeError('기존 29차 백업이 있어 덮어쓰지 않습니다.')
    backups.mkdir(parents=True)
    for rel, raw in originals.items():
        dst = backups / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(raw)
    done = []
    try:
        for rel, raw in staged.items():
            atomic_write(root / rel, raw)
            done.append(rel)
    except Exception:
        for rel in reversed(done):
            if rel in originals:
                atomic_write(root / rel, originals[rel])
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    return f'29차 설치 완료: 백엔드 {len(staged)}개 파일 수정/추가. 프론트엔드 변경 없음.'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(install(check=args.check))
        return 0
    except (OSError, RuntimeError, SyntaxError, UnicodeError, ValueError) as exc:
        print(f'29차 설치 중단: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
