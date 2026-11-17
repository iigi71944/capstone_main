"""Batch27: carry 276 prior examples forward and add 9 positive guarded cases.

Representative fixtures are NOT a proof of equivalence for arbitrary programs;
in particular the current restricted execution service blocks real file access.
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
import audit_transform_batch26 as prior
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import get_create_action_for_tag

NEW = {
    'open 사용': ('OpenTagTriplets', 'create_safe_module_io_open'),
    '파일 입출력 구조': ('FileStructureTriplets', 'create_safe_file_io_with'),
    '절차형 코드 스타일': ('ProceduralTagTriplets', 'create_safe_literal_procedural'),
}


def audit() -> dict:
    report = prior.audit()
    rows = {row['tag']: row for row in report['tags']}
    summary = report['summary']
    issues = list(summary.get('audit_issues', []))
    tried = passed = 0
    for tag, (cls, action) in NEW.items():
        item = rows.get(tag)
        if item is None or item['status'] != 'three_patterns_not_yet_proven':
            issues.append(f'{tag}: expected newly linked tag without prior triplets')
            continue
        if item['action'] != action or get_create_action_for_tag(tag) != action:
            issues.append(f'{tag}: mismatched tag-to-action mapping')
            continue
        if not callable(_get_transform_function(action)):
            issues.append(f'{tag}: dispatcher missing')
            continue
        cases = []
        for level in ('basic', 'additional', 'complex'):
            test_name = f'test_style_batch27_new_links.{cls}.test_{level}'
            ok, description = base._run_case(test_name)
            tried += 1
            passed += int(ok)
            case = {'level': level, 'test': test_name, 'passed': ok}
            if not ok:
                case['error'] = description
            cases.append(case)
        item['cases'] = cases
        item['status'] = ('three_patterns_verified' if len(cases) == 3
                          and all(case['passed'] for case in cases)
                          else 'three_pattern_tests_failed')
    summary['representative_tests'] += tried
    summary['representative_tests_passed'] += passed
    summary['explicit_triplets'] += len(NEW)
    for status in ('compare_only', 'three_patterns_verified',
                   'three_patterns_not_yet_proven', 'three_pattern_tests_failed',
                   'action_missing'):
        summary['by_status'][status] = sum(row['status'] == status for row in report['tags'])
    summary['batch27_positive_cases'] = tried
    summary['batch27_positive_cases_passed'] = passed
    summary['audit_issues'] = issues
    report['extension_note'] = ('Batch27 only transforms single-module read-only io.open '
                                'expressions and very small private literal-print helpers. '
                                'Actual file operations cannot currently be runtime-verified.')
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
        print('=== 27차 open·파일 입출력·절차형 구조 대표 감사 ===')
        print(f"전체 {summary['tags']} / 연결 {summary['linked']} / 비교전용 {summary['compare_only']}")
        print(f"3종 대표 검사 {summary['representative_tests_passed']}/{summary['representative_tests']} 통과")
        for problem in summary['audit_issues']:
            print('감사 문제:', problem)
    return 0 if (
        summary['registry_status'] == 'ok'
        and not summary['registry_issues'] and not summary['audit_issues']
        and summary['tags'] == 102
        and summary['linked'] == 95 and summary['compare_only'] == 7
        and summary['by_status']['three_patterns_verified'] == 95
        and summary['by_status']['three_patterns_not_yet_proven'] == 0
        and summary['by_status']['three_pattern_tests_failed'] == 0
        and summary['by_status']['action_missing'] == 0
        and summary['representative_tests'] == 285
        and summary['representative_tests_passed'] == 285
    ) else 1


if __name__ == '__main__':
    raise SystemExit(main())
