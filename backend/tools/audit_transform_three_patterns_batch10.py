"""Batch 10 corrected audit: only enumerate is a newly linked tag.

Prior batches 1-5 already linked four other tags; do not double count them.
Fixed fixtures only. Neither arbitrary code nor frontend files are touched.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
for place in (BACKEND, BACKEND / 'tools', BACKEND / 'tests'):
    if str(place) not in sys.path:
        sys.path.insert(0, str(place))

import audit_transform_three_patterns as base
import audit_transform_three_patterns_batch9 as prior
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import get_create_action_for_tag

PRIOR_LINKED = {
    '복합 할당': 'create_safe_augmented_assignment',
    '키워드 인자 사용': 'create_safe_keyword_call',
    '검증 로직 중심 구조': 'create_safe_validation_condition',
    '반환 중심 구조': 'create_safe_multiple_returns',
}
NEW = {
    'enumerate 사용': ('EnumerateTriplets', 'create_safe_enumerate', 'transform_to_safe_enumerate_style'),
}


def audit() -> dict:
    report = prior.audit()
    rows = {row['tag']: row for row in report['tags']}
    summary = report['summary']
    issues = list(summary.get('audit_issues', []))
    for tag, action in PRIOR_LINKED.items():
        row = rows.get(tag)
        if (not row or row.get('status') != 'three_patterns_verified'
                or row.get('action') != action
                or get_create_action_for_tag(tag) != action):
            issues.append(f'{tag}: existing action or earlier three-pattern evidence changed')

    total = passed = verified_new = 0
    for tag, (klass, action, transform_name) in NEW.items():
        row = rows.get(tag)
        if row is None or row.get('status') != 'three_patterns_not_yet_proven':
            issues.append(f'{tag}: expected newly linked, not-yet-proven tag not found')
            continue
        if row.get('action') != action or get_create_action_for_tag(tag) != action:
            issues.append(f'{tag}: registry action mismatch')
            continue
        function = _get_transform_function(action)
        if not callable(function) or function.__name__ != transform_name:
            issues.append(f'{tag}: dispatcher mismatch')
            continue
        cases = []
        for level in ('basic', 'additional', 'complex'):
            test_id = f'test_style_unmapped_patterns_batch10.{klass}.test_{level}'
            ok, details = base._run_case(test_id)
            total += 1
            passed += int(ok)
            case = {'level': level, 'test': test_id, 'passed': ok}
            if not ok:
                case['error'] = details
            cases.append(case)
        row['cases'] = cases
        row['status'] = ('three_patterns_verified' if len(cases) == 3
                         and all(item['passed'] for item in cases)
                         else 'three_pattern_tests_failed')
        verified_new += int(row['status'] == 'three_patterns_verified')

    summary['representative_tests'] += total
    summary['representative_tests_passed'] += passed
    summary['explicit_triplets'] += len(NEW)
    for status in ('three_patterns_verified', 'three_patterns_not_yet_proven',
                   'three_pattern_tests_failed', 'action_missing'):
        summary['by_status'][status] = sum(row['status'] == status for row in report['tags'])
    summary['batch10_new_linked'] = len(NEW)
    summary['batch10_reused_links'] = len(PRIOR_LINKED)
    summary['batch10_new_positive_tests'] = total
    summary['batch10_new_verified'] = verified_new
    summary['audit_issues'] = issues
    report['extension_note'] = (
        'Batch 10 adds one new linked tag (enumerate), reusing four tag links '
        'already introduced in batches 1-5. Three new representative cases. '
        'Alternative safe-augassign transform remains independently tested but '
        'does not replace the earlier public mapping or duplicate its plan. '
        'No saved style schema changes. Fixed examples are not arbitrary-code proof.'
    )
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path)
    p.add_argument('--json', action='store_true')
    args = p.parse_args()
    report = audit()
    s = report['summary']
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print('=== 10차 연결 태그 중복 정정 후 전수 검사 ===')
        print(f"전체 {s['tags']} / 연결 {s['linked']} / 비교전용 {s['compare_only']}")
        print(f"3종 대표 검증 완료 {s['by_status']['three_patterns_verified']}개")
        print(f"대표 테스트 {s['representative_tests_passed']}/{s['representative_tests']} 통과")
        for issue in s['audit_issues']:
            print('검증 문제:', issue)
    ok = (s['registry_status'] == 'ok'
          and not s['registry_issues'] and not s['audit_issues']
          and s['linked'] == 69 and s['compare_only'] == 33
          and s['by_status']['three_patterns_verified'] == 69
          and s['by_status']['three_patterns_not_yet_proven'] == 0
          and s['by_status']['three_pattern_tests_failed'] == 0
          and s['by_status']['action_missing'] == 0
          and s['representative_tests'] == 207
          and s['representative_tests_passed'] == 207)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
