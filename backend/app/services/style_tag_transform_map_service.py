
"""코딩 스타일 태그와 자동 변환 액션의 연결 규칙.

태그가 추출되었다는 사실만으로 안전한 변환이 가능한 것은 아닙니다.
실제 변환기를 호출할 수 있는 태그만 CREATE_ACTION_BY_TAG에 등록합니다.
미구현 태그는 PLANNED_TAG_FAMILY에 분리해, 향후 구현 순서를 추적합니다.
"""

from app.services.tag_rule_service import CONCEPT_TAG_RULES, SYNTAX_TAG_RULES


# style_apply_service._get_transform_function()에 실제 연결된 액션만 사용합니다.
# 여기 등록되더라도 대상 코드에 맞는 변환 패턴이 없으면 코드가 변경되지 않습니다.
CREATE_ACTION_BY_TAG: dict[str, str] = {
    # 반복 구조
    "직접 반복 사용": "create_direct_iteration",
    "인덱스 기반 반복 사용": "create_index_iteration",
    "인덱싱 중심 구조": "create_index_iteration",
    "while문": "create_while_iteration",

    # 리스트 누적과 리스트 컴프리헨션
    "리스트 누적 방식 사용": "create_append_collection",
    "리스트 메서드 호출": "create_append_collection",
    "리스트 컴프리헨션": "create_comprehension_collection",
    "컴프리헨션 기반 간결 구조": "create_comprehension_collection",

    # 딕셔너리 구조
    "딕셔너리 기반 매핑 구조": "create_mapping_style",
    "딕셔너리 컴프리헨션": "create_dict_comprehension",

    # 데이터 집계 및 상태 변경
    "데이터 집계 구조": "create_aggregation_style",
    "sum 사용": "create_sum_aggregation",
    "상태 변경 중심 구조": "create_state_update_style",

    # 데이터 필터링
    "데이터 필터링 구조": "create_filter_style",

    # 데이터 정렬
    "정렬 중심 구조": "create_sort_style",

    # 문자열 처리
    "문자열 처리 중심 구조": "create_string_chain",
    "문자열 메서드 호출": "create_string_chain",
    "f-string 사용": "create_fstring_style",

    # 검색 및 탐색
    "검색/탐색 중심 구조": "create_search_expression",
    "제너레이터 표현식": "create_search_expression",

    # 조건 구조
    "복잡한 조건식 사용": "create_structured_condition",

    # 자원 관리
    "파일/자원 관리 구조": "create_resource_context",
    "with문": "create_resource_context",

    # 함수 구성
    "함수 중심 코드 구조": "create_function_structure",
}


# 아직 전용 변환기가 구현되지 않은 태그의 작업 단위입니다.
# 실제 변환기를 구현하고 테스트한 뒤 CREATE_ACTION_BY_TAG로 옮깁니다.
PLANNED_TAG_FAMILY: dict[str, str] = {
    "세트 컴프리헨션": "set_comprehension",

    "if문": "conditional_expression",
    "lambda식": "lambda_expression",
    "return문": "return_structure",

    "객체 접근 중심 구조": "object_structure",
    "단일 책임 함수 구조": "function_decomposition",

    "데코레이터 사용": "decorator_structure",
    "모듈 의존 구조": "module_structure",
    "반복문 중심 구조": "loop_structure",
    "방어적 프로그래밍 구조": "defensive_structure",

    "예외 처리": "exception_structure",
    "예외 처리 포함 구조": "exception_structure",

    "조건문 중심 구조": "conditional_expression",

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


# 낮은 숫자일수록 먼저 구현할 변환군입니다.
# priority=3은 호출 관계 및 프로그램 의미 분석이 선행되어야 합니다.
PLANNED_FAMILY_PRIORITY: dict[str, int] = {
    "set_comprehension": 1,
    "loop_structure": 1,

    "conditional_expression": 2,
    "lambda_expression": 2,
    "return_structure": 2,
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


# 현재 자동 변환 액션에 연결되지 않은 등록 태그 전체입니다.
# 구현 예정 태그도 변환기가 연결되기 전까지 비교 대상으로 유지합니다.
COMPARE_ONLY_TAGS: set[str] = (
    set(SYNTAX_TAG_RULES) | set(CONCEPT_TAG_RULES)
) - set(CREATE_ACTION_BY_TAG)


# 과거 개선 진단 기능과의 인터페이스 호환용입니다.
REFACTOR_GUIDE_TAGS: set[str] = set()


def get_create_action_for_tag(tag_name: str) -> str | None:
    """실제로 연결된 변환 액션만 반환합니다."""
    return CREATE_ACTION_BY_TAG.get(tag_name)


def get_tag_transform_status(tag_name: str) -> str:
    """태그의 현재 지원 상태를 반환합니다.

    가능한 결과:
    - linked: 변환기가 연결된 태그
    - planned: 변환기 구현 예정 태그
    - compare_only: 비교 기능만 지원하는 태그
    - unknown: 등록되지 않은 태그

    linked는 변환기 연결만 의미하며 변환 성공을 보장하지 않습니다.
    """
    if tag_name in CREATE_ACTION_BY_TAG:
        return "linked"

    if tag_name in PLANNED_TAG_FAMILY:
        return "planned"

    if tag_name in COMPARE_ONLY_TAGS:
        return "compare_only"

    return "unknown"


def get_planned_transform_info(tag_name: str) -> dict | None:
    """아직 구현되지 않은 변환군과 우선순위를 반환합니다."""
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
    """기존 인터페이스 유지용 함수입니다."""
    return tag_name in REFACTOR_GUIDE_TAGS


def is_compare_only_tag(tag_name: str) -> bool:
    """현재 자동 변환기가 연결되지 않은 태그인지 확인합니다."""
    return tag_name in COMPARE_ONLY_TAGS
