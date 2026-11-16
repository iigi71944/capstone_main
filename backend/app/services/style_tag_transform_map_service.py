"""Map saved style tags to implemented transformations.

An action is linked only when a transformer is implemented. Runtime pattern
matching and execution validation may still leave the code unchanged.
"""

from app.services.tag_rule_service import CONCEPT_TAG_RULES, SYNTAX_TAG_RULES

CREATE_ACTION_BY_TAG: dict[str, str] = {
    # CAPSTONE_BATCH24_REGISTRY_V1: constrained builtin I/O styles.
    "import문": "create_safe_explicit_builtins_import",
    "입출력 중심 코드": "create_safe_literal_print_merge",
    # CAPSTONE_BATCH23_REGISTRY_V1: guarded break and readonly global.
    "break문": "create_safe_counted_break",
    "전역 변수 사용": "create_safe_readonly_global",
    # CAPSTONE_BATCH22_REGISTRY_V1: safe literal unpack and debug raise.
    "변수 할당": "create_safe_literal_unpack_assignments",
    "raise문": "create_safe_debug_raise",
    # CAPSTONE_BATCH21_REGISTRY_V1: narrow input and assertion styles.
    "input 사용": "create_safe_builtin_input",
    "assert문": "create_safe_debug_assert",
    # CAPSTONE_BATCH20_REGISTRY_V1: narrowly safe formatting of literal/call forms.
    "None 사용": "create_safe_empty_dict_none",
    "print 사용": "create_safe_builtin_print",
    # CAPSTONE_BATCH19_REGISTRY_V1: narrow operator conversions.
    "비교 연산": "create_safe_operator_comparison",
    "함수 호출": "create_safe_operator_call",
    # CAPSTONE_UNMAPPED_BATCH13_REGISTRY_V1: literal builtin calls only.
    "문자열 리터럴": "create_safe_string_literal",
    "숫자 리터럴": "create_safe_number_literal",
    "불리언 리터럴": "create_safe_boolean_literal",
    # CAPSTONE_UNMAPPED_BATCH12_REGISTRY_V1: three verified constrained tags.
    "continue문": "create_safe_guard_continue",
    "식별 비교": "create_safe_literal_identity",
    "산술 연산": "create_safe_arithmetic_expression",
    # CAPSTONE_UNMAPPED_BATCH11_REGISTRY_V1: three genuinely new tag links.
    "len 사용": "create_safe_literal_len",
    "zip 사용": "create_safe_literal_zip",
    "슬라이싱 사용": "create_safe_list_slice",
    # CAPSTONE_UNMAPPED_BATCH10_V1: one newly linked syntax tag; 4 earlier links preserved.
    "enumerate 사용": "create_safe_enumerate",
    # CAPSTONE_UNMAPPED_BATCH9_V1: inferred from existing saved metrics, no style-schema changes.
    "range 사용": "create_safe_literal_range",
    "논리 연산": "create_safe_nested_boolean",
    "멤버십 연산": "create_safe_known_membership",
    "sorted 사용": "create_sort_style",
    # CAPSTONE_UNMAPPED_BATCH5_V1: syntax tags use existing saved metrics, not a new storage schema.
    "인덱싱 사용": "create_safe_known_key_indexing",
    "속성 접근": "create_safe_direct_attribute",
    "키워드 인자 사용": "create_safe_keyword_call",
    "위치 인자 사용": "create_safe_positional_call",
    # CAPSTONE_UNMAPPED_BATCH4_V1: syntax preferences inferred from existing style metrics.
    "리스트 리터럴": "create_safe_list_literal",
    "딕셔너리 리터럴": "create_safe_dict_literal",
    "튜플 리터럴": "create_safe_tuple_literal",
    # CAPSTONE_UNMAPPED_BATCH3_V1: metric-directed syntax preferences; style JSON unchanged.
    "복합 할당": "create_safe_augmented_assignment",
    "딕셔너리 메서드 호출": "create_safe_dict_get",
    "for문": "create_counted_while_to_for",
    # CAPSTONE_UNMAPPED_BATCH2_V1: additional concepts, existing stored styles unchanged.
    "데이터 변환 구조": "create_safe_data_comprehension",
    "내장 함수 활용 구조": "create_safe_builtin_sum",
    "검증 로직 중심 구조": "create_safe_validation_condition",
    # CAPSTONE_UNMAPPED_BATCH1_V1: save format unchanged; previously compare-only concepts.
    "조건문 중첩 구조": "create_safe_nested_conditions",
    "깊은 중첩 구조": "create_safe_deep_conditions",
    "데이터 컬렉션 중심 구조": "create_safe_collection_literals",
    "반환 중심 구조": "create_safe_multiple_returns",
    # Batch 4: conservative, executable transformations for the four
    # previously planned architectural tag families.
    "단일 책임 함수 구조": "create_safe_validation_helper",
    "모듈 의존 구조": "create_safe_math_module_import",
    "클래스 정의": "create_safe_explicit_class",
    "클래스 중심 코드 구조": "create_safe_class_methods",
    # Batch 3: narrow method decorators, next() guards, and operator calls.
    "데코레이터 사용": "create_safe_method_decorator",
    "방어적 프로그래밍 구조": "create_safe_next_guard",
    "함수 호출 중심 구조": "create_safe_operator_call",
    # A safe lambda-assignment -> explicit def transformer already exists.
    "함수 정의": "create_safe_lambda_function",
    # Conservative, pattern-limited structural style transformations (batch 2).
    "예외 처리": "create_safe_explicit_exception",
    "예외 처리 포함 구조": "create_safe_explicit_exception",
    "함수 매개변수 활용 구조": "create_safe_keyword_call",
    "객체 접근 중심 구조": "create_safe_direct_attribute",

    # New conservative, pattern-limited transformations.
    "세트 컴프리헨션": "create_safe_set_comprehension",
    "lambda식": "create_safe_lambda_expression",
    "타입 힌트 사용": "create_safe_local_annotation",
    "타입 명시 코드 구조": "create_safe_local_annotation",
    "패턴 매칭": "create_safe_pattern_matching",
    "패턴 매칭 구조": "create_safe_pattern_matching",

    # Existing iteration styles: only transform for-loops.
    "직접 반복 사용": "create_direct_iteration",
    "인덱스 기반 반복 사용": "create_index_iteration",
    "인덱싱 중심 구조": "create_index_iteration",
    "while문": "create_while_iteration",

    # Newly implemented feature: converts counted while-loops only.
    # Its direction is gated by saved/target syntax in the plan builder.
    "반복문 중심 구조": "create_counted_while_to_for",

    # Preserve the public tag-to-action names used by existing styles/tests.
    # The plan builder upgrades these *specific tags* to safe internal actions.
    "리스트 누적 방식 사용": "create_append_collection",
    "리스트 컴프리헨션": "create_comprehension_collection",
    # Broader tags retain the existing general collection transforms.
    "리스트 메서드 호출": "create_append_collection",
    "컴프리헨션 기반 간결 구조": "create_comprehension_collection",
    "딕셔너리 기반 매핑 구조": "create_mapping_style",
    "딕셔너리 컴프리헨션": "create_dict_comprehension",

    # Existing aggregation and data handling.
    "데이터 집계 구조": "create_aggregation_style",
    "sum 사용": "create_sum_aggregation",
    "상태 변경 중심 구조": "create_state_update_style",
    "데이터 필터링 구조": "create_filter_style",
    "정렬 중심 구조": "create_sort_style",
    "문자열 처리 중심 구조": "create_string_chain",
    "문자열 메서드 호출": "create_string_chain",
    "f-string 사용": "create_fstring_style",
    "검색/탐색 중심 구조": "create_search_expression",
    "제너레이터 표현식": "create_search_expression",

    # Existing and recently added condition/return styles.
    "복잡한 조건식 사용": "create_structured_condition",
    "if문": "create_if_statement",
    "조건문 중심 구조": "create_if_statement",
    "삼항 조건식": "create_conditional_expression",
    "return문": "create_return_structure",

    # Existing resource and function styles.
    "파일/자원 관리 구조": "create_resource_context",
    "with문": "create_resource_context",
    "함수 중심 코드 구조": "create_function_structure",
}

PLANNED_TAG_FAMILY: dict[str, str] = {}

PLANNED_FAMILY_PRIORITY: dict[str, int] = {
    "set_comprehension": 1,
    "lambda_expression": 2,
    "type_annotation": 2,
    "pattern_matching": 2,
    "object_structure": 3,
    "function_decomposition": 3,
    "decorator_structure": 3,
    "module_structure": 3,
    "defensive_structure": 3,
    "exception_structure": 3,
    "class_structure": 3,
    "parameter_structure": 3,
}

COMPARE_ONLY_TAGS: set[str] = (
    set(SYNTAX_TAG_RULES) | set(CONCEPT_TAG_RULES)
) - set(CREATE_ACTION_BY_TAG)
REFACTOR_GUIDE_TAGS: set[str] = set()


def get_create_action_for_tag(tag_name: str) -> str | None:
    return CREATE_ACTION_BY_TAG.get(tag_name)


def get_tag_transform_status(tag_name: str) -> str:
    if tag_name in CREATE_ACTION_BY_TAG:
        return "linked"
    if tag_name in PLANNED_TAG_FAMILY:
        return "planned"
    if tag_name in COMPARE_ONLY_TAGS:
        return "compare_only"
    return "unknown"


def get_planned_transform_info(tag_name: str) -> dict | None:
    family = PLANNED_TAG_FAMILY.get(tag_name)
    if family is None:
        return None
    return {
        "tag": tag_name,
        "family": family,
        "priority": PLANNED_FAMILY_PRIORITY[family],
        "status": "planned",
    }


def is_refactor_guide_tag(tag_name: str) -> bool:
    return tag_name in REFACTOR_GUIDE_TAGS


def is_compare_only_tag(tag_name: str) -> bool:
    return tag_name in COMPARE_ONLY_TAGS
