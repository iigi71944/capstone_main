from app.services.tag_rule_service import enrich_concept_tag


REDUNDANT_CONCEPT_RULES = {
    # 더 구체적인 입출력 태그가 있으면 일반 입출력 태그 제거
    "입출력 중심 코드": [
        "사용자 입력 처리 구조",
        "파일 입출력 구조",
    ],

    # 더 구체적인 데이터 처리 태그가 있으면 일반 데이터 구조 태그 제거
    "데이터 컬렉션 중심 구조": [
        "딕셔너리 기반 매핑 구조",
    ],

    # 데이터 집계/필터링이 데이터 변환보다 더 구체적이면 데이터 변환 제거
    "데이터 변환 구조": [
        "데이터 집계 구조",
        "데이터 필터링 구조",
    ],

    # 인덱스 반복 개선 가능 태그가 있으면 인덱스 기반 반복 태그 제거
    "인덱스 기반 반복 사용": [
        "반복 인덱스 개선 가능 구조",
    ],

    # 타입 명시가 있으면 함수 매개변수 활용 구조보다 더 구체적으로 판단
    "함수 매개변수 활용 구조": [
        "타입 명시 코드 구조",
    ],

    # 파일 입출력 구조가 있으면 파일/자원 관리 구조는 중복 성격이 강함
    "파일/자원 관리 구조": [
        "파일 입출력 구조",
    ],

    # 비동기 처리 구조가 있으면 일반 함수 중심 구조보다 더 구체적임
    "함수 중심 코드 구조": [
        "비동기 처리 구조",
    ],

    # 깊은 중첩 구조가 있으면 조건문 중첩 구조는 하위 설명으로 판단
    "조건문 중첩 구조": [
        "깊은 중첩 구조",
    ],

    # 간결성 저하 가능 구조가 있으면 조건문/반복문 중심 구조는 일부 중복됨
    "조건문 중심 구조": [
        "간결성 저하 가능 구조",
    ],
    "반복문 중심 구조": [
        "간결성 저하 가능 구조",
    ],

    # 전역 상태 의존 구조가 있으면 상태 변경 중심 구조보다 더 구체적임
    "상태 변경 중심 구조": [
        "전역 상태 의존 구조",
    ],
}


def make_concept_tag(tag: str, score: float) -> dict:
    return enrich_concept_tag({
        "tag": tag,
        "score": score,
    })


def remove_redundant_concept_tags(concept_tags: list[dict]) -> list[dict]:
    """
    개념 태그 중복 제거 후처리 함수.

    기준:
    - 더 구체적인 개념 태그가 존재하면,
      의미가 겹치는 일반 개념 태그를 제거한다.
    - 문법 태그는 세부적으로 유지하지만,
      개념 태그는 스타일 저장과 적용에 사용되므로 대표 구조 중심으로 정리한다.
    """

    tag_names = {item.get("tag") for item in concept_tags}
    remove_targets = set()

    for general_tag, specific_tags in REDUNDANT_CONCEPT_RULES.items():
        if general_tag not in tag_names:
            continue

        for specific_tag in specific_tags:
            if specific_tag in tag_names:
                remove_targets.add(general_tag)
                break

    filtered_tags = [
        item for item in concept_tags
        if item.get("tag") not in remove_targets
    ]

    return filtered_tags


def deduplicate_concept_tags(concept_tags: list[dict]) -> list[dict]:
    """
    동일한 개념 태그가 여러 번 들어오는 경우
    score가 높은 항목을 우선 유지한다.
    """

    tag_map = {}

    for item in concept_tags:
        tag_name = item.get("tag")
        score = item.get("score", 0)

        if not tag_name:
            continue

        if tag_name not in tag_map:
            tag_map[tag_name] = item
            continue

        prev_score = tag_map[tag_name].get("score", 0)

        if score > prev_score:
            tag_map[tag_name] = item

    return list(tag_map.values())


def extract_concept_tags(metrics: dict) -> list[dict]:
    concept_tags = []

    function_count = metrics.get("function_count", 0)
    async_function_count = metrics.get("async_function_count", 0)
    class_count = metrics.get("class_count", 0)
    loop_count = metrics.get("loop_count", 0)
    if_count = metrics.get("if_count", 0)
    return_count = metrics.get("return_count", 0)
    comprehension_count = metrics.get("comprehension_count", 0)
    index_loop_count = metrics.get("index_loop_count", 0)
    direct_loop_count = metrics.get("direct_loop_count", 0)
    append_call_count = metrics.get("append_call_count", 0)
    import_count = metrics.get("import_count", 0)
    assign_count = metrics.get("assign_count", 0)
    aug_assign_count = metrics.get("aug_assign_count", 0)
    call_count = metrics.get("call_count", 0)
    bool_op_count = metrics.get("bool_op_count", 0)
    bin_op_count = metrics.get("bin_op_count", 0)
    try_count = metrics.get("try_count", 0)
    raise_count = metrics.get("raise_count", 0)
    assert_count = metrics.get("assert_count", 0)
    with_count = metrics.get("with_count", 0)
    collection_literal_count = metrics.get("collection_literal_count", 0)
    dict_literal_count = metrics.get("dict_literal_count", 0)
    subscript_count = metrics.get("subscript_count", 0)
    attribute_count = metrics.get("attribute_count", 0)
    match_count = metrics.get("match_count", 0)
    string_literal_count = metrics.get("string_literal_count", 0)
    membership_op_count = metrics.get("membership_op_count", 0)
    input_call_count = metrics.get("input_call_count", 0)
    print_call_count = metrics.get("print_call_count", 0)
    open_call_count = metrics.get("open_call_count", 0)
    sum_call_count = metrics.get("sum_call_count", 0)
    sorted_call_count = metrics.get("sorted_call_count", 0)
    enumerate_call_count = metrics.get("enumerate_call_count", 0)
    zip_call_count = metrics.get("zip_call_count", 0)
    len_call_count = metrics.get("len_call_count", 0)
    range_call_count = metrics.get("range_call_count", 0)
    string_method_call_count = metrics.get("string_method_call_count", 0)
    dict_method_call_count = metrics.get("dict_method_call_count", 0)
    type_hint_count = metrics.get("type_hint_count", 0)
    default_param_count = metrics.get("default_param_count", 0)
    positional_arg_count = metrics.get("positional_arg_count", 0)
    keyword_arg_count = metrics.get("keyword_arg_count", 0)
    global_count = metrics.get("global_count", 0)
    await_count = metrics.get("await_count", 0)
    max_function_body_length = metrics.get("max_function_body_length", 0)
    short_function_count = metrics.get("short_function_count", 0)
    max_nesting_depth = metrics.get("max_nesting_depth", 0)

    if function_count >= 1:
        concept_tags.append(make_concept_tag("함수 중심 코드 구조", 1.0))

    if class_count >= 1:
        concept_tags.append(make_concept_tag("클래스 중심 코드 구조", 1.0))

    if function_count == 0 and class_count == 0:
        concept_tags.append(make_concept_tag("절차형 코드 스타일", 1.0))

    if if_count >= 2:
        concept_tags.append(make_concept_tag("조건문 중심 구조", 0.8))

    if loop_count >= 2:
        concept_tags.append(make_concept_tag("반복문 중심 구조", 0.8))

    if index_loop_count >= 1:
        concept_tags.append(make_concept_tag("인덱스 기반 반복 사용", 1.0))
        concept_tags.append(make_concept_tag("반복 인덱스 개선 가능 구조", 0.9))

    if direct_loop_count >= 1:
        concept_tags.append(make_concept_tag("직접 반복 사용", 1.0))

    if append_call_count >= 1:
        concept_tags.append(make_concept_tag("리스트 누적 방식 사용", 0.9))

    if comprehension_count >= 1:
        concept_tags.append(make_concept_tag("컴프리헨션 기반 간결 구조", 1.0))

    if max_nesting_depth >= 2:
        concept_tags.append(make_concept_tag("조건문 중첩 구조", 0.8))

    if max_nesting_depth >= 3:
        concept_tags.append(make_concept_tag("깊은 중첩 구조", 1.0))

    if try_count >= 1:
        concept_tags.append(make_concept_tag("예외 처리 포함 구조", 0.9))

    if with_count >= 1:
        concept_tags.append(make_concept_tag("파일/자원 관리 구조", 0.9))

    if return_count >= 2:
        concept_tags.append(make_concept_tag("반환 중심 구조", 0.8))

    if collection_literal_count >= 2:
        concept_tags.append(make_concept_tag("데이터 컬렉션 중심 구조", 0.8))

    if call_count >= 3:
        concept_tags.append(make_concept_tag("함수 호출 중심 구조", 0.8))

    if assign_count + aug_assign_count >= 4:
        concept_tags.append(make_concept_tag("상태 변경 중심 구조", 0.8))

    if import_count >= 1:
        concept_tags.append(make_concept_tag("모듈 의존 구조", 0.7))

    if attribute_count >= 2:
        concept_tags.append(make_concept_tag("객체 접근 중심 구조", 0.8))

    if subscript_count >= 2:
        concept_tags.append(make_concept_tag("인덱싱 중심 구조", 0.8))

    if bool_op_count >= 1:
        concept_tags.append(make_concept_tag("복잡한 조건식 사용", 0.8))

    if raise_count >= 1 or assert_count >= 1:
        concept_tags.append(make_concept_tag("방어적 프로그래밍 구조", 0.8))

    if match_count >= 1:
        concept_tags.append(make_concept_tag("패턴 매칭 구조", 1.0))

    if if_count >= 3 or loop_count >= 3 or max_nesting_depth >= 3:
        concept_tags.append(make_concept_tag("간결성 저하 가능 구조", 0.8))

    if function_count == 0 and (loop_count >= 1 or if_count >= 1 or assign_count >= 3):
        concept_tags.append(make_concept_tag("구조화 필요 코드", 0.8))

    if print_call_count >= 1 or input_call_count >= 1 or open_call_count >= 1:
        concept_tags.append(make_concept_tag("입출력 중심 코드", 0.9))

    if if_count >= 1 and (append_call_count >= 1 or comprehension_count >= 1):
        concept_tags.append(make_concept_tag("데이터 필터링 구조", 0.9))

    if bin_op_count >= 1 or comprehension_count >= 1:
        concept_tags.append(make_concept_tag("데이터 변환 구조", 0.8))

    if sum_call_count >= 1 or aug_assign_count >= 1:
        concept_tags.append(make_concept_tag("데이터 집계 구조", 0.9))

    if loop_count >= 1 and if_count >= 1 and return_count >= 1:
        concept_tags.append(make_concept_tag("검색/탐색 중심 구조", 0.8))

    if sorted_call_count >= 1:
        concept_tags.append(make_concept_tag("정렬 중심 구조", 1.0))

    if assert_count >= 1 or raise_count >= 1 or (if_count >= 1 and bool_op_count >= 1):
        concept_tags.append(make_concept_tag("검증 로직 중심 구조", 0.8))

    if string_literal_count >= 2 or string_method_call_count >= 1:
        concept_tags.append(make_concept_tag("문자열 처리 중심 구조", 0.8))

    if dict_literal_count >= 1 or dict_method_call_count >= 1:
        concept_tags.append(make_concept_tag("딕셔너리 기반 매핑 구조", 0.8))

    if default_param_count >= 1 or positional_arg_count >= 2 or keyword_arg_count >= 1:
        concept_tags.append(make_concept_tag("함수 매개변수 활용 구조", 0.8))

    if type_hint_count >= 1:
        concept_tags.append(make_concept_tag("타입 명시 코드 구조", 1.0))

    if (
        len_call_count >= 1
        or range_call_count >= 1
        or sum_call_count >= 1
        or sorted_call_count >= 1
        or enumerate_call_count >= 1
        or zip_call_count >= 1
    ):
        concept_tags.append(make_concept_tag("내장 함수 활용 구조", 0.8))

    if input_call_count >= 1:
        concept_tags.append(make_concept_tag("사용자 입력 처리 구조", 1.0))

    if open_call_count >= 1 or with_count >= 1:
        concept_tags.append(make_concept_tag("파일 입출력 구조", 1.0))

    if async_function_count >= 1 or await_count >= 1:
        concept_tags.append(make_concept_tag("비동기 처리 구조", 1.0))

    if append_call_count >= 2 or if_count >= 3 or loop_count >= 3:
        concept_tags.append(make_concept_tag("중복 로직 포함 구조", 0.8))

    if function_count >= 2 and short_function_count >= 2:
        concept_tags.append(make_concept_tag("단일 책임 함수 구조", 0.9))

    if max_function_body_length >= 10:
        concept_tags.append(make_concept_tag("긴 함수 구조", 1.0))

    if global_count >= 1:
        concept_tags.append(make_concept_tag("전역 상태 의존 구조", 1.0))

    concept_tags = deduplicate_concept_tags(concept_tags)
    concept_tags = remove_redundant_concept_tags(concept_tags)

    return concept_tags