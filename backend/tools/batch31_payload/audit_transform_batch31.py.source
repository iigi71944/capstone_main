"""31차: seven previously compare-only tags, three real edits each.

This audit reuses all old representative fixtures, Batch29 granular fixtures,
and Batch30 conflict checks. The 7 new groups use independent subprocess
output/exit comparisons but are NOT a proof for arbitrary Python programs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
for path in (BACKEND, BACKEND / 'tests', BACKEND / 'tools'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import audit_transform_batch30 as prior
import audit_transform_three_patterns as base
from app.services.style_tag_transform_map_service import CREATE_ACTION_BY_TAG, COMPARE_ONLY_TAGS
from app.services.style_apply_service import _get_transform_function

NEW = {
    '기본 매개변수': ('DefaultParameterTriplets', 'create_safe_closed_default_parameter'),
    '가변 인자 사용': ('VarargsTriplets', 'create_safe_closed_varargs'),
    '키워드 가변 인자 사용': ('KwargsTriplets', 'create_safe_closed_kwargs'),
    '비동기 함수 정의': ('AsyncDefinitionTriplets', 'create_safe_closed_async_definition'),
    'await 사용': ('AwaitTriplets', 'create_safe_closed_await'),
    '비동기 처리 구조': ('AsyncStructureTriplets', 'create_safe_closed_async_structure'),
    '긴 함수 구조': ('LongFunctionTriplets', 'create_safe_closed_long_function'),
}


def audit() -> dict:
    report = prior.audit()
    summary = report['summary']
    rows = {row['tag']: row for row in report['tags']}
    issues = list(summary.get('audit_issues', []))
    total = passed = 0
    for tag, (klass, action) in NEW.items():
        row = rows.get(tag)
        if row is None:
            issues.append(f'{tag}: not found in canonical registry')
            continue
        if (row['status'] != 'three_patterns_not_yet_proven'
                or row['action'] != action
                or CREATE_ACTION_BY_TAG.get(tag) != action
                or not callable(_get_transform_function(action))):
            issues.append(f'{tag}: no prior evidence or action mismatch')
            continue
        checks = []
        for level in ('basic', 'additional', 'complex'):
            test_id = f'test_style_batch31_new_links.{klass}.test_{level}'
            ok, detail = base._run_case(test_id)
            total += 1
            passed += int(ok)
            entry = {'level': level, 'test': test_id, 'passed': ok}
            if not ok:
                issues.append(f'{test_id}: {detail}')
                entry['error'] = detail
            checks.append(entry)
        row['cases'] = checks
        row['status'] = ('three_patterns_verified' if len(checks) == 3 and
                         all(c['passed'] for c in checks) else 'three_pattern_tests_failed')
    for state in ('compare_only', 'three_patterns_verified',
                  'three_patterns_not_yet_proven', 'three_pattern_tests_failed',
                  'action_missing'):
        summary['by_status'][state] = sum(row['status'] == state for row in report['tags'])
    summary['representative_tests'] += total
    summary['representative_tests_passed'] += passed
    summary['explicit_triplets'] += len(NEW)
    summary['tags'] = len(report['tags'])
    summary['linked'] = len(CREATE_ACTION_BY_TAG)
    summary['compare_only'] = len(COMPARE_ONLY_TAGS)
    summary['batch31_new_passed'] = passed
    summary['batch31_new_total'] = total
    summary['audit_issues'] = issues
    report['batch31_note'] = (
        'All seven tags have constrained transformation patterns. This does NOT '
        'establish general semantic equivalence for arbitrary async programs, '
        'function introspection, module imports or external callers.')
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    report = audit()
    s = report['summary']
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print('=== 31차 잔여 7개 태그 자동 변환 대표 감사 ===')
        print(f"전체 {s['tags']} / 연결 {s['linked']} / 비교전용 {s['compare_only']}")
        print(f"전체 3종 대표 검사 {s['representative_tests_passed']}/{s['representative_tests']}")
        print(f"신규 7태그 대표 검사 {s['batch31_new_passed']}/{s['batch31_new_total']}")
        print(f"29차 세부 검사 {s['batch29_granular_passed']}/{s['batch29_granular_tests']}")
        print(f"30차 충돌 검사 {s['batch30_passed']}/{s['batch30_total']}")
        for issue in s['audit_issues']:
            print('감사 실패:', issue)
    return 0 if (
        not s['audit_issues'] and not s['registry_issues']
        and s['tags'] == 102 and s['linked'] == 102 and s['compare_only'] == 0
        and s['representative_tests'] == s['representative_tests_passed'] == 306
        and s['batch31_new_passed'] == s['batch31_new_total'] == 21
        and s['batch29_granular_passed'] == s['batch29_granular_tests'] == 12
        and s['batch30_passed'] == s['batch30_total'] == 72
        and s['by_status']['three_patterns_verified'] == 102
        and s['by_status']['compare_only'] == 0
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
