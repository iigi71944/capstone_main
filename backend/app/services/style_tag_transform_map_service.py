"""
저장된 코딩 스타일 태그를 목표 상태로 해석하는 매핑 파일입니다.

중요:
- 이 파일은 코드 개선용 모드와 별개입니다.
- 저장된 스타일의 태그를 기준으로 대상 코드를 그 스타일에 가깝게 이동시키는 것이 목적입니다.
"""

CREATE_ACTION_BY_TAG = {
    # 반복 스타일
    "직접 반복 사용": "create_direct_iteration",
    "반복 인덱스 개선 가능 구조": "create_direct_iteration",
    "인덱스 기반 반복 사용": "create_index_iteration",
    "while문": "create_while_iteration",

    # 컬렉션 / 컴프리헨션 스타일
    "리스트 누적 방식 사용": "create_append_collection",
    "리스트 메서드 호출": "create_append_collection",
    "리스트 컴프리헨션": "create_comprehension_collection",
    "딕셔너리 컴프리헨션": "create_comprehension_collection",
    "세트 컴프리헨션": "create_comprehension_collection",
    "컴프리헨션 기반 간결 구조": "create_comprehension_collection",
    "데이터 컬렉션 중심 구조": "create_collection_style",

    # 집계 / 데이터 처리
    "데이터 집계 구조": "create_aggregation_style",
    "sum 사용": "create_sum_aggregation",
    "상태 변경 중심 구조": "create_state_update_style",

    # 매핑
    "딕셔너리 기반 매핑 구조": "create_mapping_style",
    "딕셔너리 메서드 호출": "create_mapping_style",

    # 문자열
    "문자열 처리 중심 구조": "create_string_chain",
    "문자열 메서드 호출": "create_string_chain",

    # 검색 / 탐색
    "검색/탐색 중심 구조": "create_search_expression",

    # 조건 / 반환 / 구조
    "반환 중심 구조": "create_return_structure",
    "조건문 중첩 구조": "create_structured_condition",
    "깊은 중첩 구조": "create_structured_condition",
    "복잡한 조건식 사용": "create_structured_condition",
    "검증 로직 중심 구조": "create_structured_condition",

    # 파일 / 자원 관리
    "파일 입출력 구조": "create_resource_context",
    "파일/자원 관리 구조": "create_resource_context",
    "with문": "create_resource_context",

    # 함수 구조
    "함수 중심 코드 구조": "create_function_structure",
}

REFACTOR_GUIDE_TAGS = {
    "객체 접근 중심 구조",
    "중복 로직 포함 구조",
    "단일 책임 함수 구조",
    "함수 호출 중심 구조",
    "함수 매개변수 활용 구조",
    "클래스 중심 코드 구조",
    "긴 함수 구조",
    "전역 상태 의존 구조",
}

COMPARE_ONLY_TAGS = {
    "모듈 의존 구조",
    "비동기 처리 구조",
    "패턴 매칭 구조",
    "타입 명시 코드 구조",
    "내장 함수 활용 구조",
    "사용자 입력 처리 구조",
    "절차형 코드 스타일",
    "조건문 중심 구조",
    "반복문 중심 구조",
    "예외 처리 포함 구조",
    "인덱싱 중심 구조",
}


def get_create_action_for_tag(tag_name: str) -> str | None:
    return CREATE_ACTION_BY_TAG.get(tag_name)


def is_refactor_guide_tag(tag_name: str) -> bool:
    return tag_name in REFACTOR_GUIDE_TAGS


def is_compare_only_tag(tag_name: str) -> bool:
    return tag_name in COMPARE_ONLY_TAGS