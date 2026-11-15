"""Batch 7 additive three-pattern audit for the capstone project.

Reuses previously verified 39 tag triplets. Audits 16 more linked tags with
48 explicit tag->test references (27 new distinct tests + 12 old references).
No production transformers or stored style schema are modified.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / 'tests'))
sys.path.insert(0, str(BACKEND / 'tools'))

import audit_transform_three_patterns_extended as previous

# tag -> (module, testcase class, basic, additional, complex)
# All references are to positive examples that assert actual code changes.
NEW_TRIPLETS = {
    '모듈 의존 구조': (
        'test_remaining_transform_batch4', 'MathImportTests',
        'test_sqrt_forward', 'test_floor', 'test_unicode_function',
    ),
    '클래스 정의': (
        'test_remaining_transform_batch4', 'StaticClassTests',
        'test_basic', 'test_multiple_fields', 'test_unicode_fields',
    ),
    '클래스 중심 코드 구조': (
        'test_remaining_transform_batch4', 'StaticMethodClassTests',
        'test_basic', 'test_with_literal_field', 'test_multiple_methods',
    ),
    '인덱싱 중심 구조': (
        'test_safe_index_iteration_upgrade', 'IndexTests',
        'test_basic_list', 'test_break_continue', 'test_unpacking',
    ),
    '데이터 집계 구조': (
        'test_style_three_pattern_expansion_batch7', 'SumCreationTriplets',
        'test_basic', 'test_additional', 'test_complex',
    ),
    'sum 사용': (
        'test_style_three_pattern_expansion_batch7', 'SumCreationTriplets',
        'test_basic', 'test_additional', 'test_complex',
    ),
    '상태 변경 중심 구조': (
        'test_style_three_pattern_expansion_batch7', 'LoopAggregationTriplets',
        'test_basic', 'test_additional', 'test_complex',
    ),
    '딕셔너리 기반 매핑 구조': (
        'test_style_three_pattern_expansion_batch7', 'MappingCreationTriplets',
        'test_basic', 'test_additional', 'test_complex',
    ),
    '파일/자원 관리 구조': (
        'test_style_three_pattern_expansion_batch7', 'ResourceContextTriplets',
        'test_basic', 'test_additional', 'test_complex',
    ),
    'with문': (
        'test_style_three_pattern_expansion_batch7', 'ResourceContextTriplets',
        'test_basic', 'test_additional', 'test_complex',
    ),
    'if문': (
        'test_style_three_pattern_expansion_batch7', 'IfStatementTriplets',
        'test_basic', 'test_additional', 'test_complex',
    ),
    '조건문 중심 구조': (
        'test_style_three_pattern_expansion_batch7', 'IfStatementTriplets',
        'test_basic', 'test_additional', 'test_complex',
    ),
    '삼항 조건식': (
        'test_style_three_pattern_expansion_batch7', 'TernaryExpressionTriplets',
        'test_basic', 'test_additional', 'test_complex',
    ),
    'return문': (
        'test_style_three_pattern_expansion_batch7', 'ReturnStructureTriplets',
        'test_basic', 'test_additional', 'test_complex',
    ),
    '컴프리헨션 기반 간결 구조': (
        'test_style_three_pattern_expansion_batch7', 'BroadComprehensionTriplets',
        'test_basic', 'test_additional', 'test_complex',
    ),
    '리스트 메서드 호출': (
        'test_style_three_pattern_expansion_batch7', 'AppendExpansionTriplets',
        'test_basic', 'test_additional', 'test_complex',
    ),
}


# Guard against falsely attributing a positive test to a tag rewired to a
# different transformer. These names are from the actual cumulative registry.
EXPECTED_ACTION_BY_TAG = {
    '모듈 의존 구조': 'create_safe_math_module_import',
    '클래스 정의': 'create_safe_explicit_class',
    '클래스 중심 코드 구조': 'create_safe_class_methods',
    '인덱싱 중심 구조': 'create_index_iteration',
    '데이터 집계 구조': 'create_aggregation_style',
    'sum 사용': 'create_sum_aggregation',
    '상태 변경 중심 구조': 'create_state_update_style',
    '딕셔너리 기반 매핑 구조': 'create_mapping_style',
    '파일/자원 관리 구조': 'create_resource_context',
    'with문': 'create_resource_context',
    'if문': 'create_if_statement',
    '조건문 중심 구조': 'create_if_statement',
    '삼항 조건식': 'create_conditional_expression',
    'return문': 'create_return_structure',
    '컴프리헨션 기반 간결 구조': 'create_comprehension_collection',
    '리스트 메서드 호출': 'create_append_collection',
}


def audit() -> dict:
    report = previous.audit()
    tags = {item['tag']: item for item in report['tags']}
    issues = []
    new_total = 0
    new_passed = 0
    for tag, (module, cls, *functions) in NEW_TRIPLETS.items():
        record = tags.get(tag)
        if record is None or record['status'] != 'three_patterns_not_yet_proven':
            issues.append(f'{tag}: no matching unproven linked tag')
            continue
        if record['action'] != EXPECTED_ACTION_BY_TAG[tag]:
            issues.append(f"{tag}: expected action {EXPECTED_ACTION_BY_TAG[tag]}, got {record['action']}")
            continue
        cases = []
        for level, method in zip(('basic', 'additional', 'complex'), functions):
            identifier = f'{module}.{cls}.{method}'
            successful, diagnostic = previous.original_audit._run_case(identifier)
            new_total += 1
            new_passed += int(successful)
            entry = {'level': level, 'test': identifier, 'passed': successful}
            if not successful:
                entry['error'] = diagnostic
            cases.append(entry)
        record['cases'] = cases
        record['status'] = (
            'three_patterns_verified'
            if len(cases) == 3 and all(c['passed'] for c in cases)
            else 'three_pattern_tests_failed'
        )
    summary = report['summary']
    summary['representative_tests'] += new_total
    summary['representative_tests_passed'] += new_passed
    summary['explicit_triplets'] += len(NEW_TRIPLETS)
    for status in ('three_patterns_verified', 'three_patterns_not_yet_proven',
                   'three_pattern_tests_failed'):
        summary['by_status'][status] = sum(item['status'] == status for item in report['tags'])
    summary['batch7_tag_test_references'] = new_total
    summary['batch7_new_unique_tests'] = 27
    summary['batch7_existing_test_references'] = 12
    summary['audit_issues'] = issues
    report['extension_note'] = (
        'Batch 7: 16 newly classified linked tags; 48 tag-test references; '
        '27 new unique positive tests and 12 existing test references. '
        'Shared transformers share tests. Positive fixtures do not prove '
        'equivalence for arbitrary programs or end-to-end plan selection.'
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description='7차 자동 변환 기본·추가·복합 패턴 검사')
    parser.add_argument('--output', type=Path, help='JSON 보고서 파일 경로')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    result = audit()
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = result['summary']
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print('=== 7차 전체 자동 변환 3종 패턴 검증 ===')
        print(f"전체 {summary['tags']}개 / 연결 {summary['linked']}개 / 비교전용 {summary['compare_only']}개")
        print(f"3종 검증 완료 {summary['by_status']['three_patterns_verified']}개 / 근거 부족 {summary['by_status']['three_patterns_not_yet_proven']}개")
        print(f"대표 테스트 {summary['representative_tests_passed']}/{summary['representative_tests']} 통과")
        print('7차: 신규 고유 테스트 27개 / 신규 태그별 참조 48개')
        if summary['audit_issues']:
            print('검사 오류:', summary['audit_issues'])
    return (0 if summary['registry_status'] == 'ok' and not summary['registry_issues']
            and not summary['audit_issues']
            and not summary['by_status']['action_missing']
            and not summary['by_status']['three_pattern_tests_failed']
            and summary['by_status']['three_patterns_verified'] == 55
            and summary['representative_tests_passed'] == 165
            and summary['representative_tests'] == 165 else 1)


if __name__ == '__main__':
    raise SystemExit(main())
