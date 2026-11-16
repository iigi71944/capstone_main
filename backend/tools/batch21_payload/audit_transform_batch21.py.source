"""21st batch: 82 existing tag triplets plus six new positive fixtures."""
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
import audit_transform_batch20 as prior
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import get_create_action_for_tag

NEW = {
    'input 사용': ('InputTagTriplets', 'create_safe_builtin_input'),
    'assert문': ('AssertTagTriplets', 'create_safe_debug_assert'),
}


def audit() -> dict:
    report = prior.audit()
    rows = {row['tag']: row for row in report['tags']}
    summary = report['summary']
    issues = list(summary.get('audit_issues', []))
    tested = passed = 0
    for tag, (klass, action) in NEW.items():
        row = rows.get(tag)
        if row is None or row['status'] != 'three_patterns_not_yet_proven':
            issues.append(f'{tag}: expected an unverified new linked tag')
            continue
        if row['action'] != action or get_create_action_for_tag(tag) != action:
            issues.append(f'{tag}: mapping mismatch')
            continue
        if not callable(_get_transform_function(action)):
            issues.append(f'{tag}: missing dispatcher action')
            continue
        cases = []
        for level in ('basic', 'additional', 'complex'):
            case_id = f'test_style_batch21_new_links.{klass}.test_{level}'
            ok, message = base._run_case(case_id)
            tested += 1
            passed += int(ok)
            row_case = {'level': level, 'test': case_id, 'passed': ok}
            if not ok:
                row_case['error'] = message
            cases.append(row_case)
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
    summary['batch21_positive_cases'] = tested
    summary['batch21_positive_cases_passed'] = passed
    summary['audit_issues'] = issues
    report['extension_note'] = ('Batch 21 links only statically constrained '
        'builtins.input and __debug__-guarded AssertionError forms. '
        'Representative cases do not prove universal semantic equivalence.')
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
        print('=== 21차 input·assert 자동 변환 대표 감사 ===')
        print(f"전체 {s['tags']} / 연결 {s['linked']} / 비교전용 {s['compare_only']}")
        print(f"3종 대표 검사 {s['representative_tests_passed']}/{s['representative_tests']} 통과")
        for problem in s['audit_issues']:
            print('검증 문제:', problem)
    return 0 if (
        s['registry_status'] == 'ok'
        and not s['registry_issues'] and not s['audit_issues']
        and s['tags'] == 102
        and s['linked'] == 84 and s['compare_only'] == 18
        and s['by_status']['three_patterns_verified'] == 84
        and s['by_status']['three_patterns_not_yet_proven'] == 0
        and s['by_status']['three_pattern_tests_failed'] == 0
        and s['by_status']['action_missing'] == 0
        and s['representative_tests'] == 252
        and s['representative_tests_passed'] == 252
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
