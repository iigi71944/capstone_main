"""Batch 23: previous 86 linked triplets plus two new conservative triplets.

This audits selected trusted fixtures, not arbitrary-program equivalence.
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
import audit_transform_batch22 as prior
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import get_create_action_for_tag

NEW = {
    'break문': ('BreakTagTriplets', 'create_safe_counted_break'),
    '전역 변수 사용': ('GlobalTagTriplets', 'create_safe_readonly_global'),
}


def audit() -> dict:
    report = prior.audit()
    rows = {item['tag']: item for item in report['tags']}
    summary = report['summary']
    issues = list(summary.get('audit_issues', []))
    total = passed = 0
    for tag, (cls, action) in NEW.items():
        item = rows.get(tag)
        if item is None or item['status'] != 'three_patterns_not_yet_proven':
            issues.append(f'{tag}: expected unverified newly linked tag')
            continue
        if item['action'] != action or get_create_action_for_tag(tag) != action:
            issues.append(f'{tag}: expected action mapping not found')
            continue
        if not callable(_get_transform_function(action)):
            issues.append(f'{tag}: transformer dispatcher is missing')
            continue
        cases = []
        for level in ('basic', 'additional', 'complex'):
            test_id = f'test_style_batch23_new_links.{cls}.test_{level}'
            ok, detail = base._run_case(test_id)
            total += 1
            passed += int(ok)
            case = {'level': level, 'test': test_id, 'passed': ok}
            if not ok:
                case['error'] = detail
            cases.append(case)
        item['cases'] = cases
        item['status'] = ('three_patterns_verified'
                          if len(cases) == 3 and all(c['passed'] for c in cases)
                          else 'three_pattern_tests_failed')
    summary['representative_tests'] += total
    summary['representative_tests_passed'] += passed
    summary['explicit_triplets'] += len(NEW)
    for kind in ('compare_only', 'three_patterns_verified',
                 'three_patterns_not_yet_proven', 'three_pattern_tests_failed',
                 'action_missing'):
        summary['by_status'][kind] = sum(row['status'] == kind for row in report['tags'])
    summary['batch23_positive_cases'] = total
    summary['batch23_positive_cases_passed'] = passed
    summary['audit_issues'] = issues
    report['extension_note'] = (
        'Batch 23 links only narrow counted-while break guards and readonly-global '
        'patterns; representative fixtures cannot establish universal equivalence.')
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
        print('=== 23차 break문·전역 변수 사용 자동 변환 대표 감사 ===')
        print(f"전체 {s['tags']} / 연결 {s['linked']} / 비교전용 {s['compare_only']}")
        print(f"3종 대표 검사 {s['representative_tests_passed']}/{s['representative_tests']} 통과")
        for issue in s['audit_issues']:
            print('검증 문제:', issue)
    return 0 if (
        s['registry_status'] == 'ok'
        and not s['registry_issues'] and not s['audit_issues']
        and s['tags'] == 102 and s['linked'] == 88 and s['compare_only'] == 14
        and s['by_status']['three_patterns_verified'] == 88
        and s['by_status']['three_patterns_not_yet_proven'] == 0
        and s['by_status']['three_pattern_tests_failed'] == 0
        and s['by_status']['action_missing'] == 0
        and s['representative_tests'] == 264
        and s['representative_tests_passed'] == 264
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
