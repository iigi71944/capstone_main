"""Batch 13: 75 previously verified tags + 3 new representative triplets.

Nine positive cases are representative evidence, not a proof of equivalence
for arbitrary programs. All 24 remaining tags are comparison-only.
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
import audit_transform_three_patterns_batch12 as prior
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import get_create_action_for_tag


NEW = {
    '문자열 리터럴': ('StringLiteralTriplets', 'create_safe_string_literal',
                  'transform_to_safe_string_literal_style'),
    '숫자 리터럴': ('NumberLiteralTriplets', 'create_safe_number_literal',
                'transform_to_safe_number_literal_style'),
    '불리언 리터럴': ('BooleanLiteralTriplets', 'create_safe_boolean_literal',
                  'transform_to_safe_boolean_literal_style'),
}


def audit() -> dict:
    report = prior.audit()
    rows = {row['tag']: row for row in report['tags']}
    summary = report['summary']
    issues = list(summary.get('audit_issues', []))
    tested = passed = 0
    for tag, (klass, action, fn_name) in NEW.items():
        row = rows.get(tag)
        if row is None or row['status'] != 'three_patterns_not_yet_proven':
            issues.append(f'{tag}: 신규 연결 태그가 예상 상태가 아닙니다.')
            continue
        if row['action'] != action or get_create_action_for_tag(tag) != action:
            issues.append(f'{tag}: 액션 매핑 불일치')
            continue
        transformer = _get_transform_function(action)
        if not callable(transformer) or transformer.__name__ != fn_name:
            issues.append(f'{tag}: 실행기 연결 불일치')
            continue
        cases = []
        for level in ('basic', 'additional', 'complex'):
            case_id = f'test_style_unmapped_patterns_batch13.{klass}.test_{level}'
            success, detail = base._run_case(case_id)
            tested += 1
            passed += int(success)
            case = {'level': level, 'test': case_id, 'passed': success}
            if not success:
                case['error'] = detail
            cases.append(case)
        row['cases'] = cases
        row['status'] = ('three_patterns_verified'
                         if len(cases) == 3 and all(x['passed'] for x in cases)
                         else 'three_pattern_tests_failed')
    summary['representative_tests'] += tested
    summary['representative_tests_passed'] += passed
    summary['explicit_triplets'] += len(NEW)
    for kind in ('compare_only', 'three_patterns_verified',
                 'three_patterns_not_yet_proven', 'three_pattern_tests_failed',
                 'action_missing'):
        summary['by_status'][kind] = sum(row['status'] == kind for row in report['tags'])
    summary['batch13_new_links'] = len(NEW)
    summary['batch13_positive_cases_passed'] = passed
    summary['batch13_representative_tests'] = tested
    summary['audit_issues'] = issues
    report['extension_note'] = (
        'Batch 13 links only statically constrained builtin constructor calls '
        'to literal forms, with no style schema or UI changes. Tests are '
        'representative fixtures, not universal semantic equivalence proofs.'
    )
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
        print('=== 13차 신규 연결 태그 3종 대표 검사 ===')
        print(f"전체 {summary['tags']} / 연결 {summary['linked']} / 비교전용 {summary['compare_only']}")
        print(f"3종 검증 완료 {summary['by_status']['three_patterns_verified']}개")
        print(f"대표 테스트 {summary['representative_tests_passed']}/{summary['representative_tests']} 통과")
        for issue in summary['audit_issues']:
            print('검증 문제:', issue)
    return 0 if (
        summary['registry_status'] == 'ok'
        and not summary['registry_issues'] and not summary['audit_issues']
        and summary['tags'] == 102
        and summary['linked'] == 78
        and summary['compare_only'] == 24
        and summary['by_status']['three_patterns_verified'] == 78
        and summary['by_status']['three_patterns_not_yet_proven'] == 0
        and summary['by_status']['three_pattern_tests_failed'] == 0
        and summary['by_status']['action_missing'] == 0
        and summary['representative_tests'] == 234
        and summary['representative_tests_passed'] == 234
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
