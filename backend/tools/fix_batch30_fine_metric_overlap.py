"""Fix duplicate generic style gates caused by Batch29 explicit defaults.

Usage (from the capstone_main root):
  python backend/tools/fix_batch30_fine_metric_overlap.py --check
  python backend/tools/fix_batch30_fine_metric_overlap.py

Requires Batch28 policy provenance hotfix, Batch29, Batch30. This installer
changes only the style PLAN and adds a dedicated backend regression test.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PLAN = Path('backend/app/services/style_transform_plan_service.py')
METRICS = Path('backend/app/services/metric_service.py')
POLICY = Path('backend/app/services/style_tag_action_policy_service.py')
OLD_TEST = Path('backend/tests/test_style_batch30_policy_conflicts.py')
TEST = Path('backend/tests/test_style_batch30_fine_metric_overlap.py')
PAYLOAD = Path('backend/tools/batch30_overlap_fix_payload/test_style_batch30_fine_metric_overlap.py.source')
MARKER = '# CAPSTONE_BATCH30_DEFAULT_ARG_GATE_FIX_V1'
TEST_SHA256 = '7fc5348aa547e58beb957e9443ec0d309713e88bffa18fa478618cc4fb297131'


def _blob(value: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(value)).encode('ascii') + b'\0' + value).hexdigest()


def _read(path: Path) -> tuple[str, bytes, str, bool]:
    raw = path.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    data = raw[3:] if bom else raw
    if b'\n' in data.replace(b'\r\n', b'') or b'\r' in data.replace(b'\r\n', b''):
        if b'\r\n' in data:  # mixed line endings
            raise RuntimeError(f'{path}: mixed line endings are not supported')
        if b'\r' in data:
            raise RuntimeError(f'{path}: standalone CR line endings not supported')
    eol = '\r\n' if b'\r\n' in data else '\n'
    return data.replace(b'\r\n', b'\n').decode('utf-8'), raw, eol, bom


def _encode(text: str, eol: str, bom: bool) -> bytes:
    return (b'\xef\xbb\xbf' if bom else b'') + text.replace('\n', eol).encode('utf-8')


def _once(src: str, old: str, new: str, name: str) -> str:
    count = src.count(old)
    if count != 1:
        raise RuntimeError(f'{name}: expected 1 anchor, got {count}; source not modified')
    return src.replace(old, new, 1)


def patch_plan(src: str) -> str:
    if MARKER in src:
        raise RuntimeError('30차 기본 인자 수정이 이미 적용된 파일입니다.')
    original = '''def _metric_count(metrics: dict, key: str) -> int:
    value = metrics.get(key, 0)
    if type(value) is not int:
        return 0
    return max(value, 0)

'''
    updated = original + '''{marker}
def _generic_preference_metric_count(metrics: dict, key: str) -> int:
    """Count independent style evidence, excluding tracked default-arg syntax.

    - sorted(..., reverse=False): also emits a keyword argument and False literal
    - str.strip(None): also emits a positional argument and None literal
    In Batch29 each has its own measured preference/transform. Without
    subtraction, the same preference spuriously triggers generic transformers.
    For old saved styles (no fine counters), the original counts are unchanged.
    """
    captured = _metric_count(metrics, key)
    excluded = {{
        "keyword_arg_count": "sorted_reverse_false_explicit_count",
        "boolean_literal_count": "sorted_reverse_false_explicit_count",
        "positional_arg_count": "strip_none_explicit_count",
        "none_count": "strip_none_explicit_count",
    }}.get(key)
    if excluded is None:
        return captured
    return max(0, captured - _metric_count(metrics, excluded))

'''.format(marker=MARKER)
    src = _once(src, original, updated, 'metric helper')

    # Only generic code-style gates use the independent-evidence count. Fine
    # Batch29 gates and all metric *storage* continue using the true raw counts.
    fixes = [
        ('_metric_count(saved_metrics_b5, "keyword_arg_count")',
         '_generic_preference_metric_count(saved_metrics_b5, "keyword_arg_count")', 2),
        ('_metric_count(target_metrics_b5, "keyword_arg_count")',
         '_generic_preference_metric_count(target_metrics_b5, "keyword_arg_count")', 2),
        ('_metric_count(saved_metrics_b5, "positional_arg_count")',
         '_generic_preference_metric_count(saved_metrics_b5, "positional_arg_count")', 1),
        ('_metric_count(saved_b13, metric_b13)',
         '_generic_preference_metric_count(saved_b13, metric_b13)', 1),
        ('_metric_count(target_b13, metric_b13)',
         '_generic_preference_metric_count(target_b13, metric_b13)', 1),
        ('_metric_count(saved_b20, saved_metric)',
         '_generic_preference_metric_count(saved_b20, saved_metric)', 1),
        ('_metric_count(target_b20, saved_metric)',
         '_generic_preference_metric_count(target_b20, saved_metric)', 1),
    ]
    for old, new, expected in fixes:
        found = src.count(old)
        if found != expected:
            raise RuntimeError(f'gate mismatch: {old}, expected {expected}, got {found}')
        src = src.replace(old, new)

    ast.parse(src)
    for required in ('CAPSTONE_BATCH29_FINE_PLAN_V1',
                     'CAPSTONE_BATCH28_PLAN_FINALIZE_V1',
                     'finalize_tag_action_policies(actions)'):
        if required not in src:
            raise RuntimeError(f'expected existing policy missing: {required}')
    return src


def _atomic_write(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.capstone_b30_fix_', suffix='.tmp', dir=dest.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def preflight(root: Path) -> tuple[dict[Path, bytes], bytes | None]:
    if not (root / '.git').is_dir():
        raise RuntimeError('capstone_main Git 루트 폴더에서 실행해주세요.')
    for rel in (PLAN, METRICS, POLICY, OLD_TEST):
        if not (root / rel).is_file():
            raise RuntimeError(f'필요한 기존 파일이 없습니다: {rel}')
    plan, raw, eol, bom = _read(root / PLAN)
    metrics, _, _, _ = _read(root / METRICS)
    policy, _, _, _ = _read(root / POLICY)
    old_test, _, _, _ = _read(root / OLD_TEST)
    if 'CAPSTONE_BATCH29_FINE_PLAN_V1' not in plan or 'CAPSTONE_BATCH28_PLAN_FINALIZE_V1' not in plan:
        raise RuntimeError('29차/28차 계획 코드가 없습니다. 먼저 이전 패치를 적용해야 합니다.')
    if 'CAPSTONE_BATCH29_FINE_METRICS_V1' not in metrics:
        raise RuntimeError('29차 메트릭 패치가 없습니다.')
    if 'CAPSTONE_BATCH30_STABLE_POLICY_PRIORITY_V1' not in policy:
        raise RuntimeError('30차 정책 패치가 없습니다.')
    if 'test_07_sort_and_strip_coexist_without_cross_family_suppression' not in old_test:
        raise RuntimeError('30차 테스트가 없습니다.')

    file_bytes = (root / PAYLOAD).read_bytes()
    if hashlib.sha256(file_bytes).hexdigest() != TEST_SHA256:
        raise RuntimeError('새 회귀 테스트 페이로드 무결성 불일치')
    ast.parse(file_bytes.decode('utf-8'))

    marker_present = MARKER in plan
    test_present = (root / TEST).exists()
    if marker_present != test_present:
        raise RuntimeError('수정 파일이 부분 설치되었습니다. 원본 백업을 확인해주세요.')

    if marker_present:
        if plan.count(MARKER) != 1 or 'def _generic_preference_metric_count(' not in plan:
            raise RuntimeError('이미 설치된 수정 코드가 불완전합니다.')
        if (root / TEST).read_bytes() != file_bytes:
            raise RuntimeError('이미 설치된 테스트 파일 내용이 달라졌습니다.')
        if _blob(raw) == '':
            raise RuntimeError('Unexpected source checksum')
        ast.parse(plan)
        return {}, None

    patched = patch_plan(plan)
    if 'CAPSTONE_BATCH30_DEFAULT_ARG_GATE_FIX_V1' not in patched:
        raise RuntimeError('Internal marker missing')
    if (root / TEST).exists():
        raise RuntimeError('기존 이름과 충돌하는 테스트 파일이 있습니다.')
    return {
        PLAN: _encode(patched, eol, bom),
        TEST: file_bytes,
    }, raw


def install(root: Path = ROOT, *, check: bool = False) -> str:
    staged, original_plan = preflight(root)
    if not staged:
        return '30차 메트릭 중복 수정 패치가 이미 설치돼 있습니다. 변경 없음.'
    if check:
        return f'사전 검사 통과: 백엔드 수정/추가 {len(staged)}개 예정, 실제 파일 변경 없음.'
    backup_file = root / '.git' / 'capstone_batch30_overlap_backup' / PLAN
    if backup_file.exists():
        raise RuntimeError('기존 백업 경로가 존재합니다. 안전을 위해 설치를 중단합니다.')
    backup_file.parent.mkdir(parents=True, exist_ok=True)
    backup_file.write_bytes(original_plan)
    written = []
    try:
        for rel, data in staged.items():
            _atomic_write(root / rel, data)
            written.append(rel)
    except Exception:
        for rel in reversed(written):
            if rel == PLAN:
                _atomic_write(root / PLAN, original_plan)
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    return '30차 세부 메트릭 중복 해석 수정 완료: 백엔드 계획 1개 수정, 회귀 테스트 1개 추가. 프론트엔드 변경 없음.'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(install(check=args.check))
        return 0
    except (OSError, RuntimeError, ValueError, SyntaxError, UnicodeError) as error:
        print('안전 설치 중단:', error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
