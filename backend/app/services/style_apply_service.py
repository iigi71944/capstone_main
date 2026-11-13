"""Apply a saved coding style and preserve existing execution verification."""

import ast

from app.services.style_diff_service import (
    compare_after_transform,
    compare_style_with_target_code,
)
from app.services.style_transform_plan_service import build_transform_plan
from app.services.execution_validation_service import verify_execution_equivalence
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
from app.services.improvement.mapping_style_service import transform_mapping_style
from app.services.improvement.condition_style_service import transform_condition_style
from app.services.improvement.function_style_service import transform_function_style
from app.services.improvement.resource_style_service import transform_resource_style
from app.services.improvement.string_style_service import (
    transform_string_style,
    transform_to_fstring_style,
)
from app.services.improvement.search_style_service import transform_search_style
from app.services.improvement.filter_style_service import transform_to_filter_style
from app.services.improvement.sorting_style_service import transform_to_sort_style
from app.services.improvement.dict_comprehension_style_service import (
    transform_to_dict_comprehension_style,
)
from app.services.improvement.conditional_return_service import (
    transform_to_if_statement_style,
    transform_to_conditional_expression_style,
    transform_to_boolean_return_style,
)
from app.services.improvement.counted_while_to_for_service import (
    transform_counted_while_to_for,
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
    names = [item.get("tag", "") for item in tags if item.get("tag")]
    return ", ".join(names) if names else "없음"


def _get_transform_function(action: str):
    """Keep the existing action map; extend it with a while-only transformer."""
    action_map = {
        # Existing iterations
        "create_direct_iteration": transform_to_direct_iteration_style,
        "create_index_iteration": transform_to_index_iteration_style,
        "create_while_iteration": transform_to_while_iteration_style,
        # New non-overlapping while-to-for feature
        "create_counted_while_to_for": transform_counted_while_to_for,
        # Existing collections
        "create_append_collection": transform_to_append_collection_style,
        "create_comprehension_collection": transform_to_comprehension_collection_style,
        "create_collection_style": transform_to_comprehension_collection_style,
        # Existing aggregation
        "create_aggregation_style": transform_to_sum_aggregation_style,
        "create_sum_aggregation": transform_to_sum_aggregation_style,
        "create_state_update_style": transform_to_loop_aggregation_style,
        # Existing dictionaries
        "create_mapping_style": transform_mapping_style,
        "create_dict_comprehension": transform_to_dict_comprehension_style,
        # Existing strings
        "create_string_chain": transform_string_style,
        "create_fstring_style": transform_to_fstring_style,
        # Existing search / filter / sort
        "create_search_expression": transform_search_style,
        "create_filter_style": transform_to_filter_style,
        "create_sort_style": transform_to_sort_style,
        # Existing conditions and recently added condition/return transforms
        "create_structured_condition": transform_condition_style,
        "create_if_statement": transform_to_if_statement_style,
        "create_conditional_expression": transform_to_conditional_expression_style,
        "create_return_structure": transform_to_boolean_return_style,
        # Existing resources and functions
        "create_resource_context": transform_resource_style,
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
    action = action_item.get("action", "")
    tag_name = action_item.get("tag", "")
    reason = action_item.get("reason", "")
    result = {"tag": tag_name, "action": action, "status": ""}
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
    applied_rules.append(f"{reason} 적용된 변환 액션: {action}")
    return after, result


def apply_coding_style(
    code: str,
    style: dict,
    function_cases: list[dict] | None = None,
):
    """Keep the six-item API return contract and rollback semantics.

    Function cases run even if no style transformation changed the code.
    """
    applied_rules: list[str] = []
    warnings: list[str] = []
    action_results: list[dict] = []

    initial_diff = compare_style_with_target_code(style=style, code=code)
    transform_plan = build_transform_plan(initial_diff)
    transformed_code = code

    for action_item in transform_plan.get("actions", []):
        transformed_code, action_result = _apply_style_action(
            code=transformed_code,
            action_item=action_item,
            applied_rules=applied_rules,
            warnings=warnings,
        )
        action_results.append(action_result)

    if _normalize_code(code) == _normalize_code(transformed_code):
        transformed_code = code

    had_successful_transform = any(
        item.get("status") == "applied" for item in action_results
    )
    execution_verification = None
    transformation_cancelled_by_runtime = False

    if _is_changed(code, transformed_code) or function_cases is not None:
        execution_verification = verify_execution_equivalence(
            original_code=code,
            transformed_code=transformed_code,
            function_cases=function_cases,
        )
        verification_status = execution_verification.get("status")
        equivalent = execution_verification.get("equivalent")
        verification_message = execution_verification.get("message", "")

        if verification_status == "different" or equivalent is False:
            transformation_cancelled_by_runtime = True
            transformed_code = code
            applied_rules.clear()
            _add_unique(
                warnings,
                "스타일 변환 전후의 실행 결과 또는 함수 "
                "반환값에서 차이가 확인되어 전체 변환을 "
                "취소하고 원본 코드를 유지했습니다. " + verification_message,
            )
        elif verification_status == "not_verified":
            _add_unique(
                warnings,
                "스타일 변환은 수행했지만 변환 전후 코드의 "
                "실행 결과 동일성을 확인하지 못했습니다. " + verification_message,
            )

    final_diff = compare_after_transform(style=style, transformed_code=transformed_code)
    compare_only_tags = transform_plan.get("compare_only", [])
    if compare_only_tags:
        _add_unique(
            warnings,
            "다음 코딩 스타일 태그는 현재 자동 변환 규칙이 "
            "연결되어 있지 않아 코드 변경 없이 스타일 비교에만 "
            "사용됩니다: " + ", ".join(compare_only_tags),
        )

    if (
        transform_plan.get("actions")
        and not had_successful_transform
        and not transformation_cancelled_by_runtime
    ):
        has_specific_action_warning = any(
            item.get("status") in {
                "transformer_missing", "empty_result", "invalid_result", "no_safe_pattern"
            }
            for item in action_results
        )
        if not has_specific_action_warning:
            _add_unique(
                warnings,
                "자동 변환 계획은 생성되었지만 실제 코드 변경은 발생하지 않았습니다.",
            )

    if execution_verification is None:
        execution_summary = "최종 코드 변경이 없어 별도의 실행 결과 비교를 수행하지 않았습니다."
    elif execution_verification.get("status") == "equivalent":
        if execution_verification.get("function_verification") is not None:
            execution_summary = (
                "변환 전후 코드의 실제 실행 결과와 "
                "지정된 함수 테스트의 반환값·자료형이 일치함을 확인했습니다. "
                "이는 지정한 테스트 범위에서의 검증 결과입니다."
            )
        else:
            execution_summary = (
                "변환 전후 코드의 실제 실행 결과가 일치함을 확인했습니다. "
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

    summary = (
        "저장된 코딩 스타일의 문법 태그와 개념 태그를 "
        "목표 상태로 삼아 스타일 적용을 수행했습니다. "
        f"{execution_summary} "
        "최종 적용되지 않은 문법 태그: "
        f"{_format_tag_list(final_diff.get('missing_syntax_tags', []))}. "
        "최종 적용되지 않은 개념 태그: "
        f"{_format_tag_list(final_diff.get('missing_concept_tags', []))}."
    )

    return (
        transformed_code,
        summary,
        applied_rules,
        warnings,
        final_diff,
        execution_verification,
    )
