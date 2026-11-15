"""Check every style-tag action and execute explicit 3-pattern test evidence.

Run from the repository root:
    python backend/tools/audit_transform_three_patterns.py
    python backend/tools/audit_transform_three_patterns.py --json

"linked" is NOT identical to "three patterns verified". For most older
transformers the existing tests are not structured as a per-tag triplet.
This script reports them as "not_yet_proven", not as broken functionality.
Only embedded trusted tests are run. No user-entered code is executed here.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / 'tests'))

from app.services.style_apply_service import _get_transform_function
from app.services.style_tag_transform_map_service import CREATE_ACTION_BY_TAG
from app.services.style_transform_audit_service import audit_style_registry
from app.services.tag_rule_service import SYNTAX_TAG_RULES, CONCEPT_TAG_RULES


# Explicit, dedicated three-tier positive examples. These tests were built in
# batches 1..5 and older regression suites. Cases must change source patterns.
# Do not infer evidence for other tags by reusing a linked function name.
TRIPLET: dict[str, tuple[str, str, str, str, str]] = {
    '조건문 중첩 구조': ('batch1', 'NestedConditionTests', 'test_basic_two_conditions', 'test_additional_three_conditions', 'test_complex_in_function'),
    '깊은 중첩 구조': ('batch1', 'DeepConditionTests', 'test_three_terms_deep', 'test_four_terms_deep', 'test_in_function'),
    '데이터 컬렉션 중심 구조': ('batch1', 'CollectionLiteralTests', 'test_basic_list', 'test_additional_dict', 'test_complex_tuple'),
    '반환 중심 구조': ('batch1', 'MultipleReturnsTests', 'test_basic_initial_default', 'test_additional_if_else', 'test_complex_ternary'),
    '데이터 변환 구조': ('batch2', 'DataTransformTests', 'test_basic_abs', 'test_additional_str', 'test_complex_inside_function'),
    '내장 함수 활용 구조': ('batch2', 'BuiltinTransformTests', 'test_basic_augassign', 'test_additional_explicit_assign', 'test_complex_predicate_in_function'),
    '검증 로직 중심 구조': ('batch2', 'ValidationTransformTests', 'test_basic_two_nested', 'test_additional_three_nested', 'test_complex_in_function'),
    '복합 할당': ('batch3', 'AugmentedAssignmentTests', 'test_basic_plus', 'test_additional_minus', 'test_complex_multiply_inside_function'),
    '딕셔너리 메서드 호출': ('batch3', 'DictGetTests', 'test_basic_string_key', 'test_additional_integer_key', 'test_complex_function_return'),
    'for문': ('batch3', 'ApplicationIntegrationTests', 'test_for_ascending_basic', 'test_for_descending_additional', 'test_for_function_complex'),
    '리스트 리터럴': ('batch4', 'ListTag', 'test_basic_empty', 'test_additional_tuple', 'test_complex_function_condition'),
    '딕셔너리 리터럴': ('batch4', 'DictTag', 'test_basic_empty', 'test_additional_keywords', 'test_complex_function_pairs'),
    '튜플 리터럴': ('batch4', 'TupleTag', 'test_basic_empty', 'test_additional_list', 'test_complex_function'),
    '인덱싱 사용': ('batch5', 'IndexingTagTests', 'test_basic_literal_key', 'test_additional_integer_key', 'test_complex_function_return'),
    '속성 접근': ('batch5_integration', 'ExistingTransformerSmokeTests', 'test_attribute_basic', 'test_attribute_additional_string_field', 'test_attribute_complex_two_getattr_calls'),
    '키워드 인자 사용': ('batch5_integration', 'ExistingTransformerSmokeTests', 'test_keyword_basic_two_parameters', 'test_keyword_additional_three_parameters', 'test_keyword_complex_multiple_calls'),
    '위치 인자 사용': ('batch5_integration', 'ExistingTransformerSmokeTests', 'test_positional_basic', 'test_positional_additional_three_parameters', 'test_positional_complex_multiple_calls'),
    # Existing core regression suites also contain distinct positive shapes.
    '세트 컴프리헨션': ('test_remaining_transform_batch1', 'SetFamilyTests', 'test_simple_collapse', 'test_filter_collapse', 'test_two_filters'),
    '리스트 컴프리헨션': ('test_safe_list_comprehension_upgrade', 'CollapseTests', 'test_basic', 'test_filter', 'test_two_nested_filters'),
    '리스트 누적 방식 사용': ('test_safe_list_comprehension_upgrade', 'ExpandTests', 'test_basic', 'test_filter', 'test_two_filters'),
    '딕셔너리 컴프리헨션': ('test_safe_dict_comprehension_upgrade', 'CollapseTests', 'test_basic', 'test_filter', 'test_nested_filters'),
    'while문': ('test_bidirectional_loop_upgrade', 'ForToWhileTests', 'test_basic_list', 'test_for_else_break', 'test_nested_scope'),
    '직접 반복 사용': ('test_safe_index_iteration_upgrade', 'DirectTests', 'test_basic_list', 'test_preserves_index_in_body_with_enumerate', 'test_nested_function'),
    '인덱스 기반 반복 사용': ('test_safe_index_iteration_upgrade', 'IndexTests', 'test_basic_list', 'test_break_continue', 'test_unpacking'),
    '반복문 중심 구조': ('test_counted_while_to_for_upgrade', 'CountedWhileToForUpgradeTests', 'test_positive_increment', 'test_inclusive_boundary', 'test_multiple_while'),
    '함수 매개변수 활용 구조': ('test_remaining_transform_batch2', 'ParameterTests', 'test_forward', 'test_three_parameters', 'test_two_calls'),
    '객체 접근 중심 구조': ('test_remaining_transform_batch2', 'AttributeTests', 'test_getattr_forward', 'test_property', 'test_multiple_access'),
    '데코레이터 사용': ('test_remaining_transform_batch3', 'DecoratorsTests', 'test_staticmethod_forward', 'test_classmethod_forward', 'test_property_forward'),
    '단일 책임 함수 구조': ('test_remaining_transform_batch4', 'FunctionSplitTests', 'test_positive', 'test_ge_check', 'test_multifunction'),
    '방어적 프로그래밍 구조': ('test_remaining_transform_batch3', 'GuardTests', 'test_empty', 'test_nonempty', 'test_inside_function'),
    '함수 호출 중심 구조': ('test_remaining_transform_batch3', 'OperatorTests', 'test_add', 'test_sub', 'test_multiple'),
}


def _test_id(parts: tuple[str, ...], function: str) -> str:
    batch, cls, *_ = parts
    module = ('test_style_unmapped_patterns_batch5_integration' if batch == 'batch5_integration'
              else batch if batch.startswith('test_')
              else f'test_style_unmapped_patterns_{batch}')
    return f'{module}.{cls}.{function}'


def _run_case(test_id: str) -> tuple[bool, str]:
    suite = unittest.defaultTestLoader.loadTestsFromName(test_id)
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        result = unittest.TextTestRunner(stream=sink, verbosity=0).run(suite)
    passed = result.testsRun == 1 and result.wasSuccessful() and not result.skipped
    info = 'passed' if passed else sink.getvalue()[-1600:]
    return passed, info


def audit() -> dict:
    registry = audit_style_registry()
    names = sorted(set(SYNTAX_TAG_RULES) | set(CONCEPT_TAG_RULES))
    tags: list[dict] = []
    tested = 0
    passed = 0
    for tag in names:
        action = CREATE_ACTION_BY_TAG.get(tag)
        linked = action is not None
        callable_ok = callable(_get_transform_function(action)) if linked else False
        case_results = []
        if tag in TRIPLET:
            spec = TRIPLET[tag]
            for level, name in zip(('basic','additional','complex'), spec[2:]):
                test_id = _test_id(spec, name)
                ok, message = _run_case(test_id)
                tested += 1
                passed += int(ok)
                case_results.append({'level': level, 'test': test_id, 'passed': ok,
                                     **({'error': message} if not ok else {})})
        if not linked:
            grade = 'compare_only'
        elif not callable_ok:
            grade = 'action_missing'
        elif len(case_results) == 3 and all(item['passed'] for item in case_results):
            grade = 'three_patterns_verified'
        elif case_results:
            grade = 'three_pattern_tests_failed'
        else:
            grade = 'three_patterns_not_yet_proven'
        tags.append({'tag': tag, 'category': ('syntax' if tag in SYNTAX_TAG_RULES else 'concept'),
                     'action': action, 'dispatcher_callable': callable_ok,
                     'status': grade, 'cases': case_results})
    categories = {s: sum(item['status'] == s for item in tags) for s in (
        'compare_only', 'action_missing', 'three_patterns_verified',
        'three_pattern_tests_failed', 'three_patterns_not_yet_proven')}
    return {
        'summary': {'tags': len(tags), 'linked': sum(item['action'] is not None for item in tags),
                    'compare_only': categories['compare_only'],
                    'unique_public_actions': len(set(CREATE_ACTION_BY_TAG.values())),
                    'explicit_triplets': len(TRIPLET), 'representative_tests': tested,
                    'representative_tests_passed': passed,
                    'registry_status': registry['status'], 'registry_issues': registry['issues'],
                    'by_status': categories},
        'tags': tags,
        'explanation': (
            'three_patterns_not_yet_proven means no explicit per-tag 3-test manifest was '
            'established. It is NOT evidence that the transform cannot support 3 patterns. '
            'All three examples are trusted fixture tests, not a proof of general equivalence.'),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--output', type=Path, help='optional full JSON report path')
    args = parser.parse_args()
    result = audit()
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = result['summary']
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print('=== 전체 코딩 스타일 자동 변환 전수 검사 ===')
        print(f"전체 {summary['tags']}개 / 연결 {summary['linked']}개 / 비교전용 {summary['compare_only']}개")
        print('레지스트리 상태:', summary['registry_status'])
        print('3종 대표 테스트 검증:', summary['by_status']['three_patterns_verified'], '개 태그')
        print('3종 검증 근거 부족:', summary['by_status']['three_patterns_not_yet_proven'], '개 태그')
        print(f"대표 테스트: {summary['representative_tests_passed']}/{summary['representative_tests']} 통과")
        for item in result['tags']:
            if item['status'] in ('action_missing', 'three_pattern_tests_failed'):
                print('검증 오류:', item['tag'], item['status'])
        if not args.output:
            print('태그별 상세 보고서는 --output 파일명.json 옵션으로 저장할 수 있습니다.')
    return (0 if summary['registry_status'] == 'ok' and
            not summary['by_status']['action_missing'] and
            not summary['by_status']['three_pattern_tests_failed'] and
            summary['representative_tests'] == 93 and
            summary['representative_tests_passed'] == 93 else 1)


if __name__ == '__main__':
    raise SystemExit(main())
