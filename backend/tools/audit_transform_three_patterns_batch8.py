"""Batch 8 additive audit: all 64 linked tags now have 3 positive fixtures.

This extends batch 7 without editing its files. Test evidence is illustrative,
not universal semantic equivalence, pattern breadth, or end-to-end UI proof.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
for path in (BACKEND, BACKEND / 'tools', BACKEND / 'tests'):
    sys.path.insert(0, str(path))

import audit_transform_three_patterns as original_audit
import audit_transform_three_patterns_batch7 as previous
from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import get_create_action_for_tag

# tag -> (family, actual public action, actual dispatcher function)
# Some pairs share the same transformer and thus share three tests.
FAMILIES = {
    'f-string 사용': ('FStringTriplets', 'create_fstring_style', 'transform_to_fstring_style'),
    '검색/탐색 중심 구조': ('SearchTriplets', 'create_search_expression', 'transform_search_style'),
    '제너레이터 표현식': ('SearchTriplets', 'create_search_expression', 'transform_search_style'),
    '데이터 필터링 구조': ('FilterTriplets', 'create_filter_style', 'transform_to_filter_style'),
    '문자열 메서드 호출': ('StringChainTriplets', 'create_string_chain', 'transform_string_style'),
    '문자열 처리 중심 구조': ('StringChainTriplets', 'create_string_chain', 'transform_string_style'),
    '복잡한 조건식 사용': ('ConditionTriplets', 'create_structured_condition', 'transform_condition_style'),
    '정렬 중심 구조': ('SortTriplets', 'create_sort_style', 'transform_to_sort_style'),
    '함수 중심 코드 구조': ('FunctionStructureTriplets', 'create_function_structure', 'transform_function_style'),
}

LEVELS = ('basic', 'additional', 'complex')


def audit() -> dict:
    report = previous.audit()
    tags = {item['tag']: item for item in report['tags']}
    issues = list(report['summary'].get('audit_issues', []))
    counted, passed = 0, 0

    for tag, (family, expected_action, expected_function) in FAMILIES.items():
        record = tags.get(tag)
        if not record or record.get('status') != 'three_patterns_not_yet_proven':
            issues.append(f'{tag}: previously unproven linked tag not found')
            continue
        if record.get('action') != expected_action or get_create_action_for_tag(tag) != expected_action:
            issues.append(f'{tag}: public registry mapping differs from {expected_action}')
            continue
        dispatcher = _get_transform_function(expected_action)
        if not callable(dispatcher) or dispatcher.__name__ != expected_function:
            issues.append(f'{tag}: dispatcher differs from {expected_function}')
            continue
        cases = []
        for level in LEVELS:
            test_id = (f'test_style_three_pattern_expansion_batch8.'
                       f'{family}.test_{level}')
            ok, diagnostic = original_audit._run_case(test_id)
            counted += 1
            passed += int(ok)
            case = {'level': level, 'test': test_id, 'passed': ok}
            if not ok:
                case['error'] = diagnostic
            cases.append(case)
        record['cases'] = cases
        record['status'] = (
            'three_patterns_verified' if len(cases) == 3 and all(c['passed'] for c in cases)
            else 'three_pattern_tests_failed'
        )

    s = report['summary']
    s['representative_tests'] += counted
    s['representative_tests_passed'] += passed
    s['explicit_triplets'] += len(FAMILIES)
    for status in ('three_patterns_verified', 'three_patterns_not_yet_proven',
                   'three_pattern_tests_failed', 'action_missing'):
        s['by_status'][status] = sum(row['status'] == status for row in report['tags'])
    s['batch8_evidence_references'] = counted
    s['batch8_unique_positive_tests'] = 21
    s['batch8_negative_tests'] = 7
    s['audit_issues'] = issues
    report['extension_note'] = (
        'Batch 8 covers 9 tags using 7 transformer families, 21 unique positive '
        'tests, and 27 tag-to-test references. Separate 7 negative cases are '
        'run by unittest, not counted in the representative total. '
        'Each fixture asserts an AST change and matching observed execution. '
        'This does NOT prove semantic equivalence in arbitrary programs or '
        'end-to-end style selection for every saved profile.'
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description='8차 연결 태그 64개 3종 검증')
    parser.add_argument('--output', type=Path, help='저장할 JSON 보고서 파일')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    report = audit()
    summary = report['summary']
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print('=== 8차 연결 태그 3종 대표 패턴 전수 검사 ===')
        print(f"전체 {summary['tags']} / 연결 {summary['linked']} / 비교전용 {summary['compare_only']}")
        print(f"3종 대표 테스트 검증 완료 {summary['by_status']['three_patterns_verified']}개")
        print(f"근거 부족 {summary['by_status']['three_patterns_not_yet_proven']}개")
        print(f"대표 테스트 {summary['representative_tests_passed']}/{summary['representative_tests']} 통과")
        print('8차: 21개 신규 양성 테스트, 7개 안전성 테스트, 태그별 참조 27개')
        for issue in summary['audit_issues']:
            print('검사 문제:', issue)
    ok = (
        summary['registry_status'] == 'ok'
        and not summary['registry_issues']
        and not summary['audit_issues']
        and summary['linked'] == 64
        and summary['by_status']['three_patterns_verified'] == 64
        and summary['by_status']['three_patterns_not_yet_proven'] == 0
        and summary['by_status']['three_pattern_tests_failed'] == 0
        and summary['by_status']['action_missing'] == 0
        and summary['representative_tests_passed'] == 192
        and summary['representative_tests'] == 192
    )
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
