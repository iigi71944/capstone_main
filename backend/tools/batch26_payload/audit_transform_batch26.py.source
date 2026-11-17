"""Batch 26: 90 older linked triplets plus two newly implemented concept triplets.

Trusted regression fixtures only; no arbitrary program equivalence claim.
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
import audit_transform_batch24 as prior
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import get_create_action_for_tag

NEW = {
    '사용자 입력 처리 구조': ('InputStructureTriplets', 'create_safe_nested_input_structure'),
    '전역 상태 의존 구조': ('GlobalStateTriplets', 'create_safe_global_calculation'),
}


def audit():
    report = prior.audit()
    rows = {row['tag']: row for row in report['tags']}
    summary = report['summary']
    problems = list(summary.get('audit_issues', []))
    total = passed = 0
    for tag, (klass, action) in NEW.items():
        row = rows.get(tag)
        if row is None or row['status'] != 'three_patterns_not_yet_proven':
            problems.append(f'{tag}: unexpected status for new linked concept tag')
            continue
        if row['action'] != action or get_create_action_for_tag(tag) != action:
            problems.append(f'{tag}: action registry mismatch')
            continue
        if not callable(_get_transform_function(action)):
            problems.append(f'{tag}: missing dispatcher')
            continue
        cases = []
        for level in ('basic', 'additional', 'complex'):
            test_id = f'test_style_batch26_new_links.{klass}.test_{level}'
            ok, detail = base._run_case(test_id)
            total += 1
            passed += int(ok)
            item = {'level': level, 'test': test_id, 'passed': ok}
            if not ok:
                item['error'] = detail
            cases.append(item)
        row['cases'] = cases
        row['status'] = ('three_patterns_verified' if len(cases) == 3
                         and all(case['passed'] for case in cases)
                         else 'three_pattern_tests_failed')
    summary['representative_tests'] += total
    summary['representative_tests_passed'] += passed
    summary['explicit_triplets'] += len(NEW)
    for kind in ('compare_only', 'three_patterns_verified',
                 'three_patterns_not_yet_proven', 'three_pattern_tests_failed',
                 'action_missing'):
        summary['by_status'][kind] = sum(row['status'] == kind for row in report['tags'])
    summary['batch26_positive_cases'] = total
    summary['batch26_positive_cases_passed'] = passed
    summary['audit_issues'] = problems
    report['extension_note'] = (
        'Batch 26 extends nested builtin input calls and readonly global '
        'arithmetic only. Three positive cases per concept do not prove general equivalence.'
    )
    return report


def main():
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
        print('=== 26차 입력 처리 구조·전역 상태 의존 구조 자동 변환 대표 감사 ===')
        print(f"전체 {s['tags']} / 연결 {s['linked']} / 비교전용 {s['compare_only']}")
        print(f"3종 대표 검사 {s['representative_tests_passed']}/{s['representative_tests']} 통과")
        for issue in s['audit_issues']:
            print('검증 문제:', issue)
    return 0 if (
        s['registry_status'] == 'ok'
        and not s['registry_issues'] and not s['audit_issues']
        and s['tags'] == 102 and s['linked'] == 92 and s['compare_only'] == 10
        and s['by_status']['three_patterns_verified'] == 92
        and s['by_status']['three_patterns_not_yet_proven'] == 0
        and s['by_status']['three_pattern_tests_failed'] == 0
        and s['by_status']['action_missing'] == 0
        and s['representative_tests'] == 276
        and s['representative_tests_passed'] == 276
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
