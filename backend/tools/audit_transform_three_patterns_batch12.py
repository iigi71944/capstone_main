"""Batch 12 representative audit: previously verified 216 + new 9.

Representative tests for narrowly matched patterns; this does not establish
semantic equivalence for arbitrary Python programs or execution environments.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
for path in (BACKEND, BACKEND / 'tools', BACKEND / 'tests'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import audit_transform_three_patterns as base
import audit_transform_three_patterns_batch11 as prior
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import get_create_action_for_tag

NEW = {
    'continue문': ('ContinueTriplets', 'create_safe_guard_continue',
                   'transform_to_safe_guard_continue_style'),
    '식별 비교': ('IdentityTriplets', 'create_safe_literal_identity',
                'transform_to_safe_literal_identity_style'),
    '산술 연산': ('ArithmeticTriplets', 'create_safe_arithmetic_expression',
                'transform_operator_call_to_arithmetic'),
}


def audit() -> dict:
    report = prior.audit()
    rows = {row['tag']: row for row in report['tags']}
    summary = report['summary']
    issues = list(summary.get('audit_issues', []))
    tested = passed = 0
    for tag, (klass, action, function_name) in NEW.items():
        row = rows.get(tag)
        if not row or row['status'] != 'three_patterns_not_yet_proven':
            issues.append(f'{tag}: expected new linked tag not found')
            continue
        if row['action'] != action or get_create_action_for_tag(tag) != action:
            issues.append(f'{tag}: public action mismatch')
            continue
        transformer = _get_transform_function(action)
        if not callable(transformer) or transformer.__name__ != function_name:
            issues.append(f'{tag}: dispatcher mismatch')
            continue
        cases = []
        for level in ('basic', 'additional', 'complex'):
            case_id = f'test_style_unmapped_patterns_batch12.{klass}.test_{level}'
            success, detail = base._run_case(case_id)
            tested += 1
            passed += int(success)
            case = {'level': level, 'test': case_id, 'passed': success}
            if not success:
                case['error'] = detail
            cases.append(case)
        row['cases'] = cases
        row['status'] = ('three_patterns_verified'
                         if len(cases) == 3 and all(case['passed'] for case in cases)
                         else 'three_pattern_tests_failed')
    summary['representative_tests'] += tested
    summary['representative_tests_passed'] += passed
    summary['explicit_triplets'] += len(NEW)
    for status in ('three_patterns_verified', 'three_patterns_not_yet_proven',
                   'three_pattern_tests_failed', 'action_missing'):
        summary['by_status'][status] = sum(row['status'] == status for row in report['tags'])
    summary['batch12_new_links'] = len(NEW)
    summary['batch12_positive_cases_passed'] = passed
    summary['batch12_representative_tests'] = tested
    summary['audit_issues'] = issues
    report['extension_note'] = (
        'Batch 12 links continue and identity with new restricted source edits, '
        'plus arithmetic via an existing conservative operator transformer. '
        'Style persistence and UI are unchanged. Positive examples are not '
        'general program-equivalence proofs.'
    )
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path)
    p.add_argument('--json', action='store_true')
    args = p.parse_args()
    report = audit()
    summary = report['summary']
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print('=== 12차 신규 연결 태그 3종 대표 검사 ===')
        print(f"전체 {summary['tags']} / 연결 {summary['linked']} / 비교전용 {summary['compare_only']}")
        print(f"3종 검증 완료 {summary['by_status']['three_patterns_verified']}개")
        print(f"대표 테스트 {summary['representative_tests_passed']}/{summary['representative_tests']} 통과")
        for problem in summary['audit_issues']:
            print('검증 문제:', problem)
    return 0 if (
        summary['registry_status'] == 'ok'
        and not summary['registry_issues']
        and not summary['audit_issues']
        and summary['tags'] == 102
        # CAPSTONE_UNMAPPED_BATCH13_COMPAT_AUDIT12_V1: earlier triplets remain verified.
        and summary['linked'] >= 75
        and summary['compare_only'] == summary['tags'] - summary['linked']
        and summary['by_status']['three_patterns_verified'] == 75
        and summary['by_status']['three_patterns_not_yet_proven'] == summary['linked'] - 75
        and summary['by_status']['three_pattern_tests_failed'] == 0
        and summary['by_status']['action_missing'] == 0
        and summary['representative_tests'] == 225
        and summary['representative_tests_passed'] == 225
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
