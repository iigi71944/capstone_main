"""9th batch: prove three representative successes for 4 newly linked tags.

The 64 previous tags come from 8th batch; no frontend/storage changes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
for path in (BACKEND, BACKEND / 'tools', BACKEND / 'tests'):
    sys.path.insert(0, str(path))

import audit_transform_three_patterns as base_audit
import audit_transform_three_patterns_batch8 as prior
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import get_create_action_for_tag

NEW = {
    'range 사용': ('test_style_unmapped_patterns_batch9', 'RangeTriplets',
                 'create_safe_literal_range', 'transform_to_literal_range_style'),
    '논리 연산': ('test_style_unmapped_patterns_batch9', 'LogicalTriplets',
                 'create_safe_nested_boolean', 'transform_to_nested_boolean_style'),
    '멤버십 연산': ('test_style_unmapped_patterns_batch9', 'MembershipTriplets',
                 'create_safe_known_membership', 'transform_to_known_membership_style'),
    'sorted 사용': ('test_style_three_pattern_expansion_batch8', 'SortTriplets',
                 'create_sort_style', 'transform_to_sort_style'),
}


def audit() -> dict:
    report = prior.audit()
    tags = {row['tag']: row for row in report['tags']}
    summary = report['summary']
    issues = list(summary.get('audit_issues', []))
    counted = passed = 0
    for tag, (module, family, expected_action, expected_transformer) in NEW.items():
        row = tags.get(tag)
        if row is None or row.get('status') != 'three_patterns_not_yet_proven':
            issues.append(f'{tag}: expected unproven linked tag not found')
            continue
        if row['action'] != expected_action or get_create_action_for_tag(tag) != expected_action:
            issues.append(f'{tag}: registry action mismatch')
            continue
        transformer = _get_transform_function(expected_action)
        if not callable(transformer) or transformer.__name__ != expected_transformer:
            issues.append(f'{tag}: dispatcher mismatch')
            continue
        cases = []
        for level in ('basic', 'additional', 'complex'):
            test_id = f'{module}.{family}.test_{level}'
            ok, diagnostic = base_audit._run_case(test_id)
            counted += 1
            passed += int(ok)
            case = {'level': level, 'test': test_id, 'passed': ok}
            if not ok:
                case['error'] = diagnostic
            cases.append(case)
        row['cases'] = cases
        row['status'] = ('three_patterns_verified' if len(cases) == 3 and all(x['passed'] for x in cases)
                         else 'three_pattern_tests_failed')
    summary['representative_tests'] += counted
    summary['representative_tests_passed'] += passed
    summary['explicit_triplets'] += len(NEW)
    for status in ('three_patterns_verified', 'three_patterns_not_yet_proven',
                   'three_pattern_tests_failed', 'action_missing'):
        summary['by_status'][status] = sum(row['status'] == status for row in report['tags'])
    summary['batch9_new_linked'] = len(NEW)
    summary['batch9_evidence_references'] = counted
    summary['batch9_unique_positive_tests'] = 9
    summary['audit_issues'] = issues
    report['extension_note'] = (
        '9th batch links four syntax tags using existing saved metric counts. '
        'New positive fixtures: 9. Sorted usage reuses three checked sort cases. '
        'Negative tests are independent. This is representative, not proof '
        'for arbitrary Python code, and it does not change saved syntax tags.'
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
        print('=== 9차 신규 연결 태그 전수 검사 ===')
        print(f"전체 {s['tags']} / 연결 {s['linked']} / 비교전용 {s['compare_only']}")
        print(f"3종 대표 검증 완료 {s['by_status']['three_patterns_verified']}개")
        print(f"대표 테스트 {s['representative_tests_passed']}/{s['representative_tests']} 통과")
        for issue in s['audit_issues']:
            print('검증 문제:', issue)
    return 0 if (
        s['registry_status'] == 'ok' and not s['registry_issues'] and not s['audit_issues']
        and s['linked'] == 68 and s['compare_only'] == 34
        and s['by_status']['three_patterns_verified'] == 68
        and s['by_status']['three_patterns_not_yet_proven'] == 0
        and s['by_status']['three_pattern_tests_failed'] == 0
        and s['by_status']['action_missing'] == 0
        and s['representative_tests_passed'] == 204
        and s['representative_tests'] == 204
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
