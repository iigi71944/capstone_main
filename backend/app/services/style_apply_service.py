
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
from app.services.improvement.mapping_style_service import transform_mapping_style
from app.services.improvement.condition_style_service import transform_condition_style
from app.services.improvement.function_style_service import transform_function_style
from app.services.improvement.resource_style_service import transform_resource_style
from app.services.improvement.string_style_service import transform_string_style
from app.services.improvement.search_style_service import transform_search_style


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

        # 문자열
        "create_string_chain": transform_string_style,

        # 검색
        "create_search_expression": transform_search_style,

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

    실제 코드가 변경되었는지 확인하며,
    변경되지 않았거나 유효하지 않은 결과는 적용하지 않습니다.
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

    if not after.strip():
        result["status"] = "empty_result"

        _add_unique(
            warnings,
            f"'{tag_name}' 태그를 위한 변환을 시도했지만 결과 코드가 "
            "비어 있어 해당 변환을 적용하지 않았습니다.",
        )

        return code, result

    if not _is_valid_python(after):
        result["status"] = "invalid_result"

        _add_unique(
            warnings,
            f"'{tag_name}' 태그를 위한 변환을 시도했지만 변환 결과에 "
            "Python 문법 오류가 발생하여 해당 변환을 적용하지 않았습니다.",
        )

        return code, result

    if not _is_changed(before, after):
        result["status"] = "no_safe_pattern"

        _add_unique(
            warnings,
            f"'{tag_name}' 태그를 생성할 수 있는 변환기는 연결되어 있지만, "
            "현재 대상 코드에서 실행 결과를 안전하게 유지하며 변환할 수 있는 "
            "패턴을 찾지 못해 적용하지 않았습니다.",
        )

        return code, result

    result["status"] = "applied"

    applied_rules.append(
        f"{reason} 적용된 변환 액션: {action}"
    )

    return after, result


def apply_coding_style(code: str, style: dict):
    """
    저장된 코딩 스타일 적용 서비스.

    핵심 원칙:
    - 저장된 코딩 스타일의 태그를 목표 상태로 삼습니다.
    - 대상 코드의 개선 필요성이나 품질을 평가하지 않습니다.
    - 저장된 스타일의 문법 및 개념 태그에 가까워지도록 변환합니다.
    - 안전하게 자동 변환할 수 없는 스타일은 비교 대상으로 유지합니다.
    - 실제 변환 여부를 확인하고 적용 결과를 정확하게 기록합니다.
    - 변환 전후 실행 출력이 다르면 원본 코드를 복원합니다.
    - 실행 검증이 불가능하면 검증되지 않았음을 명시합니다.
    - 최종 코드를 다시 분석하여 실제 태그 상태를 반환합니다.
    """

    applied_rules: list[str] = []
    warnings: list[str] = []
    action_results: list[dict] = []

    # 1. 저장된 스타일과 대상 코드를 비교합니다.
    initial_diff = compare_style_with_target_code(
        style=style,
        code=code,
    )

    # 2. 저장된 스타일을 기준으로 변환 계획을 생성합니다.
    transform_plan = build_transform_plan(initial_diff)

    transformed_code = code

    # 3. 실제 변환이 가능한 스타일 액션을 적용합니다.
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
        item.get("status") == "applied"
        for item in action_results
    )

    execution_verification = None
    transformation_cancelled_by_runtime = False

    # 4. 실제 코드 변경이 발생했다면 실행 결과를 비교합니다.
    if _is_changed(code, transformed_code):
        execution_verification = verify_execution_equivalence(
            original_code=code,
            transformed_code=transformed_code,
        )

        verification_status = execution_verification.get("status")
        equivalent = execution_verification.get("equivalent")

        if verification_status == "different" or equivalent is False:
            transformation_cancelled_by_runtime = True
            transformed_code = code
            applied_rules.clear()

            _add_unique(
                warnings,
                "스타일 변환 자체는 수행되었지만 변환 전·후 코드의 "
                "실제 실행 출력이 서로 달라 전체 변환을 취소하고 "
                "원본 코드를 유지했습니다.",
            )

        elif verification_status == "not_verified":
            verification_message = execution_verification.get(
                "message",
                "실행 결과 동일성을 자동으로 검증하지 못했습니다.",
            )

            _add_unique(
                warnings,
                "스타일 변환은 수행되었지만 실제 실행 출력의 동일성을 "
                f"자동으로 확인하지 못했습니다. {verification_message}",
            )

    # 5. 최종 승인된 코드를 다시 분석합니다.
    final_diff = compare_after_transform(
        style=style,
        transformed_code=transformed_code,
    )

    # 6. 자동 변환을 지원하지 않는 스타일 태그를 안내합니다.
    # 코드의 개선 필요성을 평가하는 기능은 사용하지 않습니다.
    compare_only_tags = transform_plan.get("compare_only", [])

    if compare_only_tags:
        _add_unique(
            warnings,
            "다음 코딩 스타일 태그는 현재 자동 변환 규칙이 "
            "연결되어 있지 않아 코드 변경 없이 스타일 비교에만 "
            "사용됩니다: " + ", ".join(compare_only_tags),
        )

    # 7. 변환 계획은 있었지만 실제 코드가 변경되지 않은 경우입니다.
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
                "저장된 스타일 태그를 위한 자동 변환 계획은 생성되었지만 "
                "실제 코드 변경은 발생하지 않았습니다.",
            )

    # 8. 실행 검증 결과를 설명합니다.
    if execution_verification is None:
        if _is_changed(code, transformed_code):
            execution_summary = (
                "코드 변환은 발생했지만 별도의 실행 검증 결과가 없습니다."
            )
        else:
            execution_summary = (
                "최종 코드 변경이 없어 별도의 실행 출력 비교가 "
                "필요하지 않았습니다."
            )

    elif execution_verification.get("status") == "equivalent":
        execution_summary = (
            "변환 전·후 코드의 실제 실행 출력이 동일함을 확인했습니다."
        )

    elif execution_verification.get("status") == "different":
        execution_summary = (
            "변환 전·후 코드의 실제 실행 출력이 달라 변환을 취소하고 "
            "원본 코드를 유지했습니다."
        )

    else:
        execution_summary = (
            "스타일 변환은 유지했지만 변환 전·후 코드의 실제 실행 출력 "
            "동일성을 자동으로 확인하지 못했습니다."
        )

    # 9. 최종 코딩 스타일 적용 결과를 요약합니다.
    summary = (
        "저장된 코딩 스타일의 문법 태그와 개념 태그를 목표 상태로 삼아 "
        "스타일 적용을 수행했습니다. "
        "저장된 스타일에 포함된 태그와 유사한 구조가 되도록 "
        "변환을 시도했습니다. "
        f"{execution_summary} "
        f"최종 적용되지 않은 문법 태그: "
        f"{_format_tag_list(final_diff.get('missing_syntax_tags', []))}. "
        f"최종 적용되지 않은 개념 태그: "
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
