"""30차: 16개 태그 정책 순서 안정화 + 72개 충돌 회귀 테스트.

capstone_main 루트에서 다음을 실행합니다.
  python backend/tools/install_batch30.py --check
  python backend/tools/install_batch30.py

29차 설치가 완료된 상태만 허용합니다. 프론트엔드 파일을 수정하지 않습니다.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = Path('backend/tools/batch30_payload')
POLICY = Path('backend/app/services/style_tag_action_policy_service.py')
REGISTRY = Path('backend/app/services/style_tag_transform_map_service.py')
PLAN = Path('backend/app/services/style_transform_plan_service.py')
METRICS = Path('backend/app/services/metric_service.py')
APPLY = Path('backend/app/services/style_apply_service.py')

BASE_POLICY_BLOB = '388cf0634e0b897d73df2da314ac04eaa1f38a5f'
BASE_REGISTRY_BLOB = 'ae4a4c9126738ff91c688e50e41dbc9f64bcdb3c'

NEW = {
    Path('backend/tests/test_style_batch30_policy_conflicts.py'):
        PAYLOAD / 'test_style_batch30_policy_conflicts.py.source',
    Path('backend/tools/audit_transform_batch30.py'):
        PAYLOAD / 'audit_transform_batch30.py.source',
}

MARK = '# CAPSTONE_BATCH30_STABLE_POLICY_PRIORITY_V1'
PAYLOAD_SHA256 = {
    'backend/tools/batch30_payload/audit_transform_batch30.py.source': '4707f54212356ac1b4ebb73378654262554b971fdb9d03ee20f8c27e75db94b3',
    'backend/tools/batch30_payload/test_style_batch30_policy_conflicts.py.source': 'c4df16ac6e7bf742a33617e7f0fe690288c86b6cd9d0748fda10dc8febc05684',
}


def blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def read_source(path: Path):
    raw = path.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    body = raw[3:] if bom else raw
    if b'\r\n' in body and b'\n' in body.replace(b'\r\n', b''):
        raise RuntimeError(f'{path}: LF/CRLF 혼용 중단')
    if b'\r' in body.replace(b'\r\n', b''):
        raise RuntimeError(f'{path}: 단독 CR 줄바꿈 거부')
    eol = '\r\n' if b'\r\n' in body else '\n'
    text = body.replace(b'\r\n', b'\n').decode('utf-8')
    return text, raw, eol, bom


def encode_source(src: str, eol: str, bom: bool) -> bytes:
    return (b'\xef\xbb\xbf' if bom else b'') + src.replace('\n', eol).encode('utf-8')


def patch_policy(source: str) -> str:
    before = '''def _preference(index: int, item: dict, policy: dict) -> tuple[int, int, int]:
'''
    if source.count(before) != 1:
        raise RuntimeError('정책 우선순위 함수 형태가 예상과 다릅니다.')
    source = source.replace(before, '''def _preference(index: int, item: dict, policy: dict) -> tuple[int, int, int, int]:
''', 1)
    before = '''        0 if policy["role"] == "concept_structure" else 1,
        index,
'''
    after = '''        0 if policy["role"] == "concept_structure" else 1,
        # CAPSTONE_BATCH30_STABLE_POLICY_PRIORITY_V1: resolve equal-role
        # pairs by their declared policy order, not incoming action order.
        policy["index"],
        index,
'''
    if source.count(before) != 1:
        raise RuntimeError('정책 tie-break 소스 위치를 찾지 못했습니다.')
    source = source.replace(before, after, 1)
    ast.parse(source)
    return source


def preflight(root: Path):
    if not (root / '.git').is_dir():
        raise RuntimeError('capstone_main Git 루트에서 실행해주세요.')
    required = {
        REGISTRY: ('CREATE_ACTION_BY_TAG',),
        PLAN: ('CAPSTONE_BATCH29_FINE_PLAN_V1', 'CAPSTONE_BATCH28_PLAN_FINALIZE_V1',
               'finalize_tag_action_policies(actions)'),
        METRICS: ('CAPSTONE_BATCH29_FINE_METRICS_V1',),
        APPLY: ('CAPSTONE_BATCH29_DISPATCH_MAP_V1',),
        POLICY: ('CAPSTONE_BATCH29_POLICY_ALLOWED_V1',),
    }
    inputs = {}
    for rel, markers in required.items():
        path = root / rel
        if not path.is_file():
            raise RuntimeError(f'필수 설치 파일이 없습니다: {rel}')
        text, raw, eol, bom = read_source(path)
        if any(marker not in text for marker in markers):
            raise RuntimeError(f'28차 핫픽스/29차 패치 확인 실패: {rel}')
        inputs[rel] = (text, raw, eol, bom)
    if blob(inputs[REGISTRY][0].encode('utf-8')) != BASE_REGISTRY_BLOB:
        raise RuntimeError('태그 레지스트리가 27~29차 기준과 다릅니다.')

    present_policy = MARK in inputs[POLICY][0]
    if present_policy:
        # A changed or partial installation may be dangerous; if the marker is
        # already there, validate the full expected result rather than guessing.
        post = patch_policy_from_base_marker(root, inputs[POLICY][0])
        if not post:
            raise RuntimeError('30차 정책 패치가 예상과 다르게 수정되어 있습니다.')
    else:
        if blob(inputs[POLICY][0].encode('utf-8')) != BASE_POLICY_BLOB:
            raise RuntimeError('29차 정책 파일 버전이 일치하지 않습니다.')

    staged = {}
    originals = {}
    if not present_policy:
        source, raw, eol, bom = inputs[POLICY]
        staged[POLICY] = encode_source(patch_policy(source), eol, bom)
        originals[POLICY] = raw

    existing_new = []
    for rel, payload_rel in NEW.items():
        payload = root / payload_rel
        if not payload.is_file():
            raise RuntimeError(f'ZIP 내부 파일이 누락됐습니다: {payload_rel}')
        contents = payload.read_bytes()
        if hashlib.sha256(contents).hexdigest() != PAYLOAD_SHA256[str(payload_rel).replace('\\', '/')]:
            raise RuntimeError(f'ZIP 패치 페이로드 무결성 실패: {payload_rel}')
        ast.parse(contents.decode('utf-8'))
        dest = root / rel
        if dest.exists():
            if not dest.is_file() or dest.read_bytes() != contents:
                raise RuntimeError(f'새 파일 충돌: {rel}')
            existing_new.append(True)
        else:
            staged[rel] = contents
            existing_new.append(False)

    # Every target must be either uninstalled or fully installed. Do not add
    # files to a repo containing an incomplete/mismatched 30th patch.
    is_all_existing = present_policy and all(existing_new)
    is_all_new = (not present_policy and not any(existing_new))
    if not (is_all_existing or is_all_new):
        raise RuntimeError('30차 일부만 설치된 상태입니다. 자동 덮어쓰기 없이 중단합니다.')
    return staged, originals


def patch_policy_from_base_marker(root: Path, src: str) -> bool:
    # The marker must uniquely occur at the intended priority location and
    # annotation must match. For current-source equality use stable checksum.
    if src.count(MARK) != 1:
        return False
    if 'def _preference(index: int, item: dict, policy: dict) -> tuple[int, int, int, int]:' not in src:
        return False
    if '        policy["index"],\n        index,\n' not in src:
        return False
    try:
        ast.parse(src)
    except SyntaxError:
        return False
    return True


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.capstone_b30_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def install(root: Path = ROOT, check: bool = False):
    staged, originals = preflight(root)
    if not staged:
        return '30차 개발 패치가 이미 설치되어 있습니다. 변경 없음.'
    if check:
        return f'30차 설치 사전 검사 통과: {len(staged)}개 파일 준비, 수정 없음.'
    backup = root / '.git/capstone_batch30_backups'
    if backup.exists():
        raise RuntimeError('30차 백업 폴더가 이미 존재합니다. 덮어쓰지 않습니다.')
    backup.mkdir(parents=True)
    for rel, raw in originals.items():
        dest = backup / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    written = []
    try:
        for rel, content in staged.items():
            atomic_write(root / rel, content)
            written.append(rel)
    except Exception:
        for rel in reversed(written):
            if rel in originals:
                atomic_write(root / rel, originals[rel])
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    return f'30차 설치 완료: 백엔드 {len(staged)}개 파일 수정/추가. 프론트엔드는 변경하지 않았습니다.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(install(check=args.check))
        return 0
    except (OSError, RuntimeError, ValueError, SyntaxError, UnicodeError) as err:
        print('30차 설치 중단:', err)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
