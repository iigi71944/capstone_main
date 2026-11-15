"""Extend the proven 3-pattern audit without modifying the original audit.

Existing audit remains authoritative for the original 31 tags; this adds 8
linked tags using five explicitly tested transformer families. Some tags
share a transformer and thus share the same three cases; do not interpret
these as 24 independent scenarios.
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

import audit_transform_three_patterns as original_audit

# Each entry (module, class, basic, additional, complex).
EXTRA_TRIPLETS = {
    'lambda식': ('test_style_three_pattern_expansion_batch6', 'LambdaCreationTriplets',
                 'test_basic_one_parameter', 'test_additional_two_parameters', 'test_complex_nested_function'),
    '함수 정의': ('test_style_three_pattern_expansion_batch6', 'FunctionCreationTriplets',
                 'test_basic_one_parameter', 'test_additional_two_parameters', 'test_complex_nested_function'),
    '패턴 매칭': ('test_style_three_pattern_expansion_batch6', 'PatternCreationTriplets',
                 'test_basic_integer_branches', 'test_additional_three_string_branches', 'test_complex_method_body'),
    '패턴 매칭 구조': ('test_style_three_pattern_expansion_batch6', 'PatternCreationTriplets',
                 'test_basic_integer_branches', 'test_additional_three_string_branches', 'test_complex_method_body'),
    '예외 처리': ('test_style_three_pattern_expansion_batch6', 'ExceptionCreationTriplets',
                 'test_basic_value_error', 'test_additional_key_error', 'test_complex_two_context_managers'),
    '예외 처리 포함 구조': ('test_style_three_pattern_expansion_batch6', 'ExceptionCreationTriplets',
                 'test_basic_value_error', 'test_additional_key_error', 'test_complex_two_context_managers'),
    '타입 힌트 사용': ('test_style_three_pattern_expansion_batch6', 'TypeHintCreationTriplets',
                 'test_basic_integer_assignment', 'test_additional_string_assignment', 'test_complex_multiple_types_inside_function'),
    '타입 명시 코드 구조': ('test_style_three_pattern_expansion_batch6', 'TypeHintCreationTriplets',
                 'test_basic_integer_assignment', 'test_additional_string_assignment', 'test_complex_multiple_types_inside_function'),
}


def audit() -> dict:
    base = original_audit.audit()
    tags = {row['tag']: row for row in base['tags']}
    issues = []
    total_new = 0
    passed_new = 0
    for tag, (module, cls, *functions) in EXTRA_TRIPLETS.items():
        row = tags.get(tag)
        if row is None or row['status'] != 'three_patterns_not_yet_proven':
            issues.append(f'{tag}: expected a linked tag without existing evidence')
            continue
        cases = []
        for level, method in zip(('basic', 'additional', 'complex'), functions):
            test_id = f'{module}.{cls}.{method}'
            ok, err = original_audit._run_case(test_id)
            total_new += 1
            passed_new += int(ok)
            item = {'level': level, 'test': test_id, 'passed': ok}
            if not ok:
                item['error'] = err
            cases.append(item)
        row['cases'] = cases
        row['status'] = ('three_patterns_verified' if len(cases) == 3 and
                         all(case['passed'] for case in cases) else 'three_pattern_tests_failed')
    summary = base['summary']
    summary['representative_tests'] += total_new
    summary['representative_tests_passed'] += passed_new
    summary['explicit_triplets'] += len(EXTRA_TRIPLETS)
    for status in ('three_patterns_verified', 'three_patterns_not_yet_proven',
                   'three_pattern_tests_failed'):
        summary['by_status'][status] = sum(row['status'] == status for row in base['tags'])
    summary['additional_unique_test_methods'] = 15
    summary['additional_tag_evidence_references'] = 24
    summary['audit_issues'] = issues
    base['extension_note'] = (
        '8 tags share 5 transformer families and 15 distinct tests, with 24 '
        'tag-to-test references. This is positive evidence for three shapes, '
        'not proof of all Python behaviors or of end-to-end style-plan selection.'
    )
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description='기존 31개 + 6차 신규 8개 태그 3종 테스트 검사')
    parser.add_argument('--output', type=Path, help='JSON report path')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    report = audit()
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    s = report['summary']
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print('=== 6차 태그별 기본형·추가형·복합형 확장 검사 ===')
        print(f"전체 {s['tags']} / 연결 {s['linked']} / 비교전용 {s['compare_only']}")
        print(f"3종 검증 완료 {s['by_status']['three_patterns_verified']}개 / 근거 부족 {s['by_status']['three_patterns_not_yet_proven']}개")
        print(f"대표 테스트 {s['representative_tests_passed']}/{s['representative_tests']} 통과")
        print('신규 고유 테스트 15개, 새 태그별 참조 24개 (공유 변환기 포함)')
        if s['audit_issues']:
            print('검사 오류:', s['audit_issues'])
    return (0 if s['registry_status'] == 'ok' and not s['registry_issues']
            and not s['audit_issues'] and not s['by_status']['action_missing']
            and not s['by_status']['three_pattern_tests_failed']
            and s['by_status']['three_patterns_verified'] == 39
            and s['representative_tests_passed'] == 117 else 1)


if __name__ == '__main__':
    raise SystemExit(main())
