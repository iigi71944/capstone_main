"""Batch 11 tag-wide evidence audit: 69 previous + 3 new linked tags.

Runs three concrete positive cases for each new tag and all prior 207 cases.
This is representative evidence, not general program-equivalence proof.
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
import audit_transform_three_patterns_batch10 as prior
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import get_create_action_for_tag

NEW = {
    'len 사용': ('LenTriplets', 'create_safe_literal_len',
               'transform_to_safe_literal_len_style'),
    'zip 사용': ('ZipTriplets', 'create_safe_literal_zip',
               'transform_to_safe_literal_zip_style'),
    '슬라이싱 사용': ('SliceTriplets', 'create_safe_list_slice',
                   'transform_to_safe_list_slice_style'),
}


def audit() -> dict:
    report = prior.audit()
    tags = {row['tag']: row for row in report['tags']}
    summary = report['summary']
    issues = list(summary.get('audit_issues', []))
    tested = 0
    passed = 0
    for tag, (klass, action, expected_function) in NEW.items():
        row = tags.get(tag)
        if not row or row.get('status') != 'three_patterns_not_yet_proven':
            issues.append(f'{tag}: not an expected new linked tag')
            continue
        if row.get('action') != action or get_create_action_for_tag(tag) != action:
            issues.append(f'{tag}: action registration mismatch')
            continue
        transformer = _get_transform_function(action)
        if not callable(transformer) or transformer.__name__ != expected_function:
            issues.append(f'{tag}: runtime dispatcher mismatch')
            continue
        cases = []
        for level in ('basic', 'additional', 'complex'):
            case_id = f'test_style_unmapped_patterns_batch11.{klass}.test_{level}'
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
    summary['batch11_new_links'] = len(NEW)
    summary['batch11_representative_tests'] = tested
    summary['batch11_positive_cases_passed'] = passed
    summary['audit_issues'] = issues
    report['extension_note'] = (
        'Batch 11 links three formerly compare-only syntax tags; saved style '
        'preferences come exclusively from existing metric counters. '
        'Tests only fixed, constrained examples, not arbitrary Python code.'
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
        print('=== 11차 신규 연결 태그 3종 대표 검사 ===')
        print(f"전체 {summary['tags']} / 연결 {summary['linked']} / 비교전용 {summary['compare_only']}")
        print(f"3종 검증 완료 {summary['by_status']['three_patterns_verified']}개")
        print(f"대표 테스트 {summary['representative_tests_passed']}/{summary['representative_tests']} 통과")
        for issue in summary['audit_issues']:
            print('검증 문제:', issue)
    return 0 if (
        summary['registry_status'] == 'ok'
        and not summary['registry_issues']
        and not summary['audit_issues']
        and summary['tags'] == 102
        and summary['linked'] == 72
        and summary['compare_only'] == 30
        and summary['by_status']['three_patterns_verified'] == 72
        and summary['by_status']['three_patterns_not_yet_proven'] == 0
        and summary['by_status']['three_pattern_tests_failed'] == 0
        and summary['by_status']['action_missing'] == 0
        and summary['representative_tests'] == 216
        and summary['representative_tests_passed'] == 216
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
