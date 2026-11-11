
import ast

from app.services.style_diff_service import (
    compare_after_transform,
    compare_style_with_target_code,
)
from app.services.style_transform_plan_service import build_transform_plan
from app.services.execution_validation_service import (
    verify_execution_equivalence,
)

from app.services.improvement.iteration_style_service import (
    transform_to_direct_iteration_style,
    transform_to_index_iteration_style,
    transform_to_while_iteration_style,
)
from app.services.improvement.collection_style_service import (
    transform_to_append_collection_style,
    transform_to_comprehension_collection_style,
)
from app.services.improvement.aggregation_style_service import (
    transform_to_loop_aggregation_style,
    transform_to_sum_aggregation_style,
)
from app.services.improvement.mapping_style_service import (
    transform_mapping_style,
)
from app.services.improvement.condition_style_service import (
    transform_condition_style,
)
from app.services.improvement.function_style_service import (
    transform_function_style,
)
from app.services.improvement.resource_style_service import (
    transform_resource_style,
)
from app.services.improvement.string_style_service import (
    transform_string_style,
    transform_to_fstring_style,
)
from app.services.improvement.search_style_service import (
    transform_search_style,
)
from app.services.improvement.filter_style_service import (
    transform_to_filter_style,
)
from app.services.improvement.sorting_style_service import (
    transform_to_sort_style,
)
from app.services.improvement.dict_comprehension_style_service import (
    transform_to_dict_comprehension_style,
)


def _normalize_code(code: str) -> str:
    try:
        return ast.unparse(ast.parse(code)).strip()
    except Exception:
        return code.strip()


def _is_changed(before: str, after: str) -> bool:
    return _normalize_code(before) != _normalize_code(after)


def _is_valid_python(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def _add_unique(items: list[str], message: str) -> None:
    if message not in items:
        items.append(message)


def _format_tag_list(tags: list[dict]) -> str:
    names = [
        item.get("tag", "")
        for item in tags
        if item.get("tag")
    ]

    if not names:
        return "없음"

    return ", ".join(names)


def _get_transform_function(action: str):
    """
    스타일 변환 액션과 실제 변환기를 연결합니다.

    기존에 구현한 자동 변환 기능을 유지합니다.
    """

    action_map = {
        # 반복 방식
        "create_direct_iteration": transform_to_direct_iteration_style,
        "create_index_iteration": transform_to_index_iteration_style,
        "create_while_iteration": transform_to_while_iteration_style,

        # 컬렉션과 컴프리헨션
        "create_append_collection": transform_to_append_collection_style,
        "create_comprehension_collection": transform_to_comprehension_collection_style,
        "create_collection_style": transform_to_comprehension_collection_style,

        # 데이터 집계
        "create_aggregation_style": transform_to_sum_aggregation_style,
        "create_sum_aggregation": transform_to_sum_aggregation_style,
        "create_state_update_style": transform_to_loop_aggregation_style,

        # 딕셔너리
        "create_mapping_style": transform_mapping_style,
        "create_dict_comprehension": transform_to_dict_comprehension_style,

        # 문자열
        "create_string_chain": transform_string_style,
        "create_fstring_style": transform_to_fstring_style,

        # 검색 및 탐색
        "create_search_expression": transform_search_style,

        # 데이터 필터링
        "create_filter_style": transform_to_filter_style,

        # 데이터 정렬
        "create_sort_style": transform_to_sort_style,

        # 조건과 반환
        "create_return_structure": transform_condition_style,
        "create_structured_condition": transform_condition_style,

        # 파일 및 자원 관리
        "create_resource_context": transform_resource_style,

        # 함수 구조
        "create_function_structure": transform_function_style,
    }

    return action_map.get(action)


def _apply_style_action(
    *,
    code: str,
    action_item: dict,
    applied_rules: list[str],
    warnings: list[str],
) -> tuple[str, dict]:
    """
    하나의 스타일 변환 액션을 적용합니다.

    변환 결과가 유효한 Python 코드인지 확인합니다.
    변환 전후에 실제 코드 변경이 없는 경우에는
    적용 성공으로 기록하지 않습니다.
    """

    action = action_item.get("action", "")
    tag_name = action_item.get("tag", "")
    reason = action_item.get("reason", "")

    result = {
        "tag": tag_name,
        "action": action,
        "status": "",
    }

    transform_func = _get_transform_function(action)

    if transform_func is None:
        result["status"] = "transformer_missing"

        _add_unique(
            warnings,
            f"'{tag_name}' 태그를 생성하기 위한 변환기({action})가 "
            "현재 연결되어 있지 않아 자동 변환하지 않았습니다.",
        )

        return code, result

    before = code
    after = transform_func(code)

    if not isinstance(after, str) or not after.strip():
        result["status"] = "empty_result"

        _add_unique(
            warnings,
            f"'{tag_name}' 태그를 위한 변환을 시도했지만 "
            "유효한 코드 문자열을 얻지 못했습니다.",
        )

        return code, result

    if not _is_valid_python(after):
        result["status"] = "invalid_result"

        _add_unique(
            warnings,
            f"'{tag_name}' 태그를 위한 변환을 시도했지만 "
            "Python 문법 오류가 발생하여 적용하지 않았습니다.",
        )

        return code, result

    if not _is_changed(before, after):
        result["status"] = "no_safe_pattern"

        _add_unique(
            warnings,
            f"'{tag_name}' 태그의 변환기는 연결되어 있지만 "
            "현재 대상 코드에서 안전하게 변환할 수 있는 "
            "패턴을 찾지 못했습니다.",
        )

        return code, result

    result["status"] = "applied"

    applied_rules.append(
        f"{reason} 적용된 변환 액션: {action}"
    )

    return after, result


def apply_coding_style(
    code: str,
    style: dict,
    function_cases: list[dict] | None = None,
):
    """
    저장된 코딩 스타일을 대상 Python 코드에 적용합니다.

    기본 동작:
    1. 저장된 스타일과 대상 코드를 비교합니다.
    2. 부족한 스타일 태그에 대한 변환 계획을 수립합니다.
    3. 실제 변환기를 호출합니다.
    4. 변환 결과의 Python 문법을 확인합니다.
    5. 변환 전후 코드를 실행해 결과를 비교합니다.
    6. 차이가 확인되면 전체 변환을 취소합니다.
    7. 최종 코드의 태그와 메트릭을 다시 분석합니다.

    추가 동작:
    function_cases가 주어진 경우 지정한 함수들을
    같은 입력값으로 호출해 반환값과 자료형도 비교합니다.

    function_cases가 None이면 기존의 실행 검증만 사용합니다.

    검증 결과:
    - equivalent: 지정된 테스트에서 관찰된 결과 일치
    - different: 결과 차이를 발견하여 원본 복원
    - not_verified: 결과의 동일성을 확인하지 못함

    not_verified일 때는 기존 정책에 따라 변환 코드를
    유지하되 검증되지 않았다는 경고를 표시합니다.

    실행 결과의 일치가 모든 입력에 대한 동작 동일성을
    보장하는 것은 아닙니다.
    """

    applied_rules: list[str] = []
    warnings: list[str] = []
    action_results: list[dict] = []

    # 1. 저장된 스타일과 대상 코드를 비교합니다.
    initial_diff = compare_style_with_target_code(
        style=style,
        code=code,
    )

    # 2. 변환 계획을 생성합니다.
    transform_plan = build_transform_plan(initial_diff)

    transformed_code = code

    # 3. 계획에 포함된 변환 액션을 적용합니다.
    for action_item in transform_plan.get("actions", []):
        transformed_code, action_result = _apply_style_action(
            code=transformed_code,
            action_item=action_item,
            applied_rules=applied_rules,
            warnings=warnings,
        )

        action_results.append(action_result)

    # AST 기준으로 실제 코드 구조가 같다면
    # 불필요한 변환 결과를 유지하지 않습니다.
    if _normalize_code(code) == _normalize_code(transformed_code):
        transformed_code = code

    had_successful_transform = any(
        item.get("status") == "applied"
        for item in action_results
    )

    execution_verification = None
    transformation_cancelled_by_runtime = False

    # 4. 실제 코드 변경이 발생한 경우 실행 결과를 검증합니다.
    if _is_changed(code, transformed_code):
        execution_verification = verify_execution_equivalence(
            original_code=code,
            transformed_code=transformed_code,
            function_cases=function_cases,
        )

        verification_status = execution_verification.get("status")
        equivalent = execution_verification.get("equivalent")

        verification_message = execution_verification.get(
            "message",
            "",
        )

        # 실행 출력이나 함수 반환값에서 차이가 발견되었다면
        # 기존 정책대로 전체 변환을 취소합니다.
        if verification_status == "different" or equivalent is False:
            transformation_cancelled_by_runtime = True

            transformed_code = code
            applied_rules.clear()

            _add_unique(
                warnings,
                "스타일 변환 전후의 실행 결과 또는 함수 "
                "반환값에서 차이가 확인되어 전체 변환을 "
                "취소하고 원본 코드를 유지했습니다. "
                + verification_message,
            )

        # 검증하지 못한 코드는 동일하다고 주장하지 않습니다.
        elif verification_status == "not_verified":
            _add_unique(
                warnings,
                "스타일 변환은 수행했지만 변환 전후 코드의 "
                "실행 결과 동일성을 확인하지 못했습니다. "
                + verification_message,
            )

    # 5. 최종적으로 유지할 코드를 다시 분석합니다.
    final_diff = compare_after_transform(
        style=style,
        transformed_code=transformed_code,
    )

    # 6. 비교 전용 태그는 따로 안내합니다.
    compare_only_tags = transform_plan.get(
        "compare_only",
        [],
    )

    if compare_only_tags:
        _add_unique(
            warnings,
            "다음 코딩 스타일 태그는 현재 자동 변환 규칙이 "
            "연결되어 있지 않아 코드 변경 없이 스타일 비교에만 "
            "사용됩니다: " + ", ".join(compare_only_tags),
        )

    # 7. 변환 계획은 있었지만 실제 변경이 없는 경우입니다.
    if (
        transform_plan.get("actions")
        and not had_successful_transform
        and not transformation_cancelled_by_runtime
    ):
        has_specific_action_warning = any(
            item.get("status") in {
                "transformer_missing",
                "empty_result",
                "invalid_result",
                "no_safe_pattern",
            }
            for item in action_results
        )

        if not has_specific_action_warning:
            _add_unique(
                warnings,
                "자동 변환 계획은 생성되었지만 "
                "실제 코드 변경은 발생하지 않았습니다.",
            )

    # 8. 실행 검증 결과를 요약합니다.
    if execution_verification is None:
        execution_summary = (
            "최종 코드 변경이 없어 별도의 실행 결과 "
            "비교를 수행하지 않았습니다."
        )

    elif execution_verification.get("status") == "equivalent":
        if execution_verification.get("function_verification") is not None:
            execution_summary = (
                "변환 전후 코드의 실제 실행 결과와 "
                "지정된 함수 테스트의 반환값·자료형이 "
                "일치함을 확인했습니다. "
                "이는 지정한 테스트 범위에서의 검증 결과입니다."
            )

        else:
            execution_summary = (
                "변환 전후 코드의 실제 실행 결과가 "
                "일치함을 확인했습니다. "
                "함수 반환값이 별도로 검증된 것은 아닙니다."
            )

    elif execution_verification.get("status") == "different":
        execution_summary = (
            "실행 결과 또는 함수 반환값의 차이가 확인되어 "
            "전체 변환을 취소하고 원본 코드를 유지했습니다."
        )

    else:
        execution_summary = (
            "스타일 변환은 유지했지만 실행 결과 또는 "
            "함수 반환값의 동일성을 확인하지 못했습니다."
        )

    # 9. 최종 코딩 스타일 적용 결과를 요약합니다.
    summary = (
        "저장된 코딩 스타일의 문법 태그와 개념 태그를 "
        "목표 상태로 삼아 스타일 적용을 수행했습니다. "
        f"{execution_summary} "
        "최종 적용되지 않은 문법 태그: "
        f"{_format_tag_list(final_diff.get('missing_syntax_tags', []))}. "
        "최종 적용되지 않은 개념 태그: "
        f"{_format_tag_list(final_diff.get('missing_concept_tags', []))}."
    )

    # 기존 API 호출부와의 호환성을 위해
    # 기존의 여섯 가지 반환값을 그대로 유지합니다.
    return (
        transformed_code,
        summary,
        applied_rules,
        warnings,
        final_diff,
        execution_verification,
    )
