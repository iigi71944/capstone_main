"""Map saved style tags to implemented transformations.

An action is linked only when a transformer is implemented. Runtime pattern
matching and execution validation may still leave the code unchanged.
"""

from app.services.tag_rule_service import CONCEPT_TAG_RULES, SYNTAX_TAG_RULES

CREATE_ACTION_BY_TAG: dict[str, str] = {
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

PLANNED_TAG_FAMILY: dict[str, str] = {
    "세트 컴프리헨션": "set_comprehension",
    "lambda식": "lambda_expression",
    "객체 접근 중심 구조": "object_structure",
    "단일 책임 함수 구조": "function_decomposition",
    "데코레이터 사용": "decorator_structure",
    "모듈 의존 구조": "module_structure",
    "방어적 프로그래밍 구조": "defensive_structure",
    "예외 처리": "exception_structure",
    "예외 처리 포함 구조": "exception_structure",
    "클래스 정의": "class_structure",
    "클래스 중심 코드 구조": "class_structure",
    "타입 명시 코드 구조": "type_annotation",
    "타입 힌트 사용": "type_annotation",
    "패턴 매칭": "pattern_matching",
    "패턴 매칭 구조": "pattern_matching",
    "함수 매개변수 활용 구조": "parameter_structure",
    "함수 정의": "function_decomposition",
    "함수 호출 중심 구조": "function_decomposition",
}

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
