"""Batch 19 registered-tag triplet audit: historical 234 + six new positives.

Runs trusted unittest fixtures only; not an equivalence proof for arbitrary code.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
for path in (BACKEND, BACKEND / 'tools', BACKEND / 'tests'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import audit_transform_three_patterns as base
import audit_transform_three_patterns_batch13 as prior
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import get_create_action_for_tag

NEW = {
    '함수 호출': ('FunctionCallTagTriplets', 'create_safe_operator_call'),
    '비교 연산': ('ComparisonTagTriplets', 'create_safe_operator_comparison'),
}


def audit() -> dict:
    report = prior.audit()
    rows = {row['tag']: row for row in report['tags']}
    summary = report['summary']
    issues = list(summary.get('audit_issues', []))
    tested = passed = 0
    for tag, (class_name, action) in NEW.items():
        row = rows.get(tag)
        if row is None or row['status'] != 'three_patterns_not_yet_proven':
            issues.append(f'{tag}: expected unverified new linked tag')
            continue
        if row['action'] != action or get_create_action_for_tag(tag) != action:
            issues.append(f'{tag}: dispatcher mapping mismatch')
            continue
        if not callable(_get_transform_function(action)):
            issues.append(f'{tag}: transformer missing')
            continue
        cases = []
        for level in ('basic', 'additional', 'complex'):
            case_id = f'test_style_batch19_new_links.{class_name}.test_{level}'
            success, detail = base._run_case(case_id)
            tested += 1
            passed += int(success)
            case = {'level': level, 'test': case_id, 'passed': success}
            if not success:
                case['error'] = detail
            cases.append(case)
        row['cases'] = cases
        row['status'] = ('three_patterns_verified' if len(cases) == 3
                         and all(item['passed'] for item in cases)
                         else 'three_pattern_tests_failed')
    summary['representative_tests'] += tested
    summary['representative_tests_passed'] += passed
    summary['explicit_triplets'] += len(NEW)
    for kind in ('compare_only', 'three_patterns_verified',
                 'three_patterns_not_yet_proven', 'three_pattern_tests_failed',
                 'action_missing'):
        summary['by_status'][kind] = sum(row['status'] == kind for row in report['tags'])
    summary['batch19_positive_cases'] = tested
    summary['batch19_positive_cases_passed'] = passed
    summary['audit_issues'] = issues
    report['extension_note'] = (
        'Batch 19 adds only statically constrained operator-expression conversions. '
        'Representative fixtures do not establish universal semantic equivalence.')
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    report = audit()
    summary = report['summary']
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print('=== 19차 신규 자동 변환 태그 2종 대표 검사 ===')
        print(f"전체 {summary['tags']} / 연결 {summary['linked']} / 비교전용 {summary['compare_only']}")
        print(f"3종 대표 검사 {summary['representative_tests_passed']}/{summary['representative_tests']} 통과")
        for issue in summary['audit_issues']:
            print('검증 문제:', issue)
    return 0 if (
        summary['registry_status'] == 'ok'
        and not summary['registry_issues'] and not summary['audit_issues']
        and summary['tags'] == 102
        and summary['linked'] == 80 and summary['compare_only'] == 22
        and summary['by_status']['three_patterns_verified'] == 80
        and summary['by_status']['three_patterns_not_yet_proven'] == 0
        and summary['by_status']['three_pattern_tests_failed'] == 0
        and summary['by_status']['action_missing'] == 0
        and summary['representative_tests'] == 240
        and summary['representative_tests_passed'] == 240
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
