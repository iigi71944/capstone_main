"""Batch 24: 88 historical verified links + two new representative triplets.

This executes trusted unit tests only; it does not prove equivalence for
arbitrary code and must not run submitted user code.
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
import audit_transform_batch23 as prior
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import get_create_action_for_tag

NEW = {
    'import문': ('ImportTagTriplets', 'create_safe_explicit_builtins_import'),
    '입출력 중심 코드': ('OutputTagTriplets', 'create_safe_literal_print_merge'),
}


def audit():
    report = prior.audit()
    rows = {row['tag']: row for row in report['tags']}
    summary = report['summary']
    problems = list(summary.get('audit_issues', []))
    tested = passed = 0
    for tag, (klass, action) in NEW.items():
        row = rows.get(tag)
        if row is None or row['status'] != 'three_patterns_not_yet_proven':
            problems.append(f'{tag}: expected newly linked tag with no older triplet')
            continue
        if row['action'] != action or get_create_action_for_tag(tag) != action:
            problems.append(f'{tag}: action registry mismatch')
            continue
        if not callable(_get_transform_function(action)):
            problems.append(f'{tag}: dispatch is not callable')
            continue
        results = []
        for level in ('basic', 'additional', 'complex'):
            test_id = f'test_style_batch24_new_links.{klass}.test_{level}'
            okay, detail = base._run_case(test_id)
            tested += 1
            passed += int(okay)
            record = {'level': level, 'test': test_id, 'passed': okay}
            if not okay:
                record['error'] = detail
            results.append(record)
        row['cases'] = results
        row['status'] = ('three_patterns_verified' if len(results) == 3
                         and all(entry['passed'] for entry in results)
                         else 'three_pattern_tests_failed')
    summary['representative_tests'] += tested
    summary['representative_tests_passed'] += passed
    summary['explicit_triplets'] += len(NEW)
    for state in ('compare_only', 'three_patterns_verified',
                  'three_patterns_not_yet_proven', 'three_pattern_tests_failed',
                  'action_missing'):
        summary['by_status'][state] = sum(row['status'] == state for row in report['tags'])
    summary['batch24_positive_cases'] = tested
    summary['batch24_positive_cases_passed'] = passed
    summary['audit_issues'] = problems
    report['extension_note'] = (
        'Batch 24 only rewrites constrained module-level builtin printing. '
        'These fixtures are not a universal proof of semantic equivalence.'
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
        print('=== 24차 import문·입출력 중심 코드 자동 변환 대표 감사 ===')
        print(f"전체 {s['tags']} / 연결 {s['linked']} / 비교전용 {s['compare_only']}")
        print(f"3종 대표 검사 {s['representative_tests_passed']}/{s['representative_tests']} 통과")
        for issue in s['audit_issues']:
            print('검증 문제:', issue)
    return 0 if (
        s['registry_status'] == 'ok'
        and not s['registry_issues'] and not s['audit_issues']
        and s['tags'] == 102 and s['linked'] == 90 and s['compare_only'] == 12
        and s['by_status']['three_patterns_verified'] == 90
        and s['by_status']['three_patterns_not_yet_proven'] == 0
        and s['by_status']['three_pattern_tests_failed'] == 0
        and s['by_status']['action_missing'] == 0
        and s['representative_tests'] == 270
        and s['representative_tests_passed'] == 270
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
