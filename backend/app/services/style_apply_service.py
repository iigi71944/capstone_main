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
from app.services.improvement.refactor_style_service import (
    build_compare_only_warnings,
    build_refactor_warnings,
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

    if not names:
        return "없음"

    return ", ".join(names)


def _get_transform_function(action: str):
    action_map = {
        "create_direct_iteration": transform_to_direct_iteration_style,
        "create_index_iteration": transform_to_index_iteration_style,
        "create_while_iteration": transform_to_while_iteration_style,

        "create_append_collection": transform_to_append_collection_style,
        "create_comprehension_collection": transform_to_comprehension_collection_style,
        "create_collection_style": transform_to_comprehension_collection_style,

        "create_aggregation_style": transform_to_sum_aggregation_style,
        "create_sum_aggregation": transform_to_sum_aggregation_style,
        "create_state_update_style": transform_to_loop_aggregation_style,

        "create_mapping_style": transform_mapping_style,

        "create_string_chain": transform_string_style,
        "create_search_expression": transform_search_style,

        "create_return_structure": transform_condition_style,
        "create_structured_condition": transform_condition_style,

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
) -> str:
    action = action_item.get("action", "")
    tag_name = action_item.get("tag", "")
    reason = action_item.get("reason", "")

    transform_func = _get_transform_function(action)

    if transform_func is None:
        _add_unique(
            warnings,
            f"'{tag_name}' 태그를 생성하기 위한 변환기({action})가 아직 연결되어 있지 않아 변환하지 않았습니다.",
        )
        return code

    before = code
    after = transform_func(code)

    if not after.strip():
        _add_unique(
            warnings,
            f"{reason} 그러나 변환 결과가 비어 있어 원본 코드를 유지했습니다.",
        )
        return code

    if not _is_valid_python(after):
        _add_unique(
            warnings,
            f"{reason} 그러나 변환 결과에 Python 문법 오류가 있어 원본 코드를 유지했습니다.",
        )
        return code

    if not _is_changed(before, after):
        _add_unique(
            warnings,
            f"{reason} 그러나 현재 대상 코드가 해당 태그를 안전하게 생성할 수 있는 패턴과 일치하지 않아 변환하지 않았습니다.",
        )
        return code

    applied_rules.append(
        f"{reason} 적용된 변환 액션: {action}"
    )

    return after


def apply_coding_style(code: str, style: dict):
    """
    코딩 스타일 적용 V3.

    핵심 철학:
    - 저장된 코딩 스타일의 태그를 목표 상태로 삼습니다.
    - 대상 코드를 '더 좋은 코드'로 바꾸는 것이 아니라,
      저장된 스타일의 문법/개념 태그에 가까워지도록 구조와 형태를 변경합니다.
    - 변환 후보가 생성되면 가능한 경우 원본 코드와 변환 코드의
      실제 실행 출력을 비교합니다.
    - 실제 실행 출력이 다르면 변환을 취소하고 원본 코드를 유지합니다.
    - 실행 검증이 불가능한 경우에는 이를 명확히 표시하고,
      기존의 보수적인 스타일 변환 결과를 유지합니다.
    - 변환 완료 후 최종 승인된 코드를 다시 분석하여
      실제 최종 태그 상태를 반환합니다.
    """

    applied_rules: list[str] = []
    warnings: list[str] = []

    initial_diff = compare_style_with_target_code(
        style=style,
        code=code,
    )

    transform_plan = build_transform_plan(initial_diff)

    transformed_code = code

    for action_item in transform_plan.get("actions", []):
        transformed_code = _apply_style_action(
            code=transformed_code,
            action_item=action_item,
            applied_rules=applied_rules,
            warnings=warnings,
        )

    if _normalize_code(code) == _normalize_code(transformed_code):
        transformed_code = code

    execution_verification = None

    if _is_changed(code, transformed_code):
        execution_verification = verify_execution_equivalence(
            original_code=code,
            transformed_code=transformed_code,
        )

        verification_status = execution_verification.get("status")
        equivalent = execution_verification.get("equivalent")

        if verification_status == "different" or equivalent is False:
            transformed_code = code
            applied_rules.clear()

            _add_unique(
                warnings,
                "스타일 변환 후 실행 출력이 원본 코드와 달라 "
                "변환을 취소하고 원본 코드를 유지했습니다.",
            )

        elif verification_status == "not_verified":
            verification_message = execution_verification.get(
                "message",
                "실행 결과 동일성을 자동으로 검증하지 못했습니다.",
            )

            _add_unique(
                warnings,
                "스타일 변환은 수행되었지만 실제 실행 결과의 동일성을 "
                f"자동으로 확인하지 못했습니다. {verification_message}",
            )

    final_diff = compare_after_transform(
        style=style,
        transformed_code=transformed_code,
    )

    for warning in build_refactor_warnings(
        transform_plan.get("refactor_guides", [])
    ):
        _add_unique(warnings, warning)

    for warning in build_compare_only_warnings(
        transform_plan.get("compare_only", [])
    ):
        _add_unique(warnings, warning)

    if not applied_rules:
        _add_unique(
            warnings,
            "저장된 스타일 태그를 기준으로 변환 계획을 생성했지만, "
            "실행 결과를 유지하면서 안전하게 생성 가능한 스타일 태그 패턴이 "
            "발견되지 않아 원본 코드를 유지했습니다.",
        )

    if execution_verification is None:
        execution_summary = (
            "코드 변경이 없어 별도의 실행 결과 비교가 필요하지 않았습니다."
        )
    elif execution_verification.get("status") == "equivalent":
        execution_summary = (
            "변환 전·후 코드의 실제 실행 출력이 동일함을 확인했습니다."
        )
    elif execution_verification.get("status") == "different":
        execution_summary = (
            "변환 전·후 코드의 실제 실행 출력이 달라 변환을 취소했습니다."
        )
    else:
        execution_summary = (
            "변환 전·후 코드의 실제 실행 출력 동일성을 자동으로 "
            "확인하지 못했습니다."
        )

    summary = (
        "저장된 코딩 스타일의 문법 태그와 개념 태그를 목표 상태로 삼아 "
        "스타일 적용을 수행했습니다. "
        "대상 코드를 단순히 개선하는 것이 아니라, 저장된 스타일에 포함된 "
        "태그와 유사한 구조가 되도록 변환을 시도했습니다. "
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