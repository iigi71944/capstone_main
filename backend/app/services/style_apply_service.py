"""Apply a saved coding style and preserve existing execution verification."""

import ast

from app.services.style_diff_service import (
    compare_after_transform,
    compare_style_with_target_code,
)
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_action_outcome_service import (
    summarize_action_outcomes,
    format_action_outcome_summary,
    format_cancelled_action_warnings,
)
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
from app.services.improvement.safe_list_comprehension_service import (
    transform_for_append_to_list_comprehension,
    transform_list_comprehension_to_for_append,
)
from app.services.improvement.safe_dict_comprehension_service import (
    transform_for_assignment_to_dict_comprehension,
    transform_dict_comprehension_to_for_assignment,
)


from app.services.improvement.safe_set_comprehension_service import (
    transform_for_add_to_set_comprehension,
    transform_set_comprehension_to_for_add,
)
from app.services.improvement.safe_syntax_patterns_service import (
    transform_lambda_to_def,
    transform_def_to_lambda,
    transform_if_to_match,
    transform_match_to_if,
    transform_add_local_type_hints,
    transform_remove_local_type_hints,
)

from app.services.improvement.safe_structural_patterns_service import (
    transform_suppress_to_try,
    transform_try_to_suppress,
    transform_positional_to_keyword_call,
    transform_keyword_to_positional_call,
    transform_getattr_to_attribute,
    transform_attribute_to_getattr,
)
from app.services.improvement.safe_remaining_patterns_service import (
    transform_assignment_to_decorator,
    transform_decorator_to_assignment,
    transform_next_default_to_try,
    transform_try_to_next_default,
    transform_arithmetic_to_operator_call,
    transform_operator_call_to_arithmetic,
)


from app.services.improvement.safe_architecture_patterns_service import (
    transform_extract_validation_helper,
    transform_inline_validation_helper,
    transform_from_math_to_module,
    transform_math_module_to_from,
    transform_type_to_class,
    transform_type_to_class_with_methods,
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
        # Batch 3 conservative transforms and their reverse callables.
        # Batch 4: narrow architecture pattern transforms.
        "create_safe_validation_helper": transform_extract_validation_helper,
        "create_safe_inline_validation": transform_inline_validation_helper,
        "create_safe_math_module_import": transform_from_math_to_module,
        "create_safe_math_member_import": transform_math_module_to_from,
        "create_safe_explicit_class": transform_type_to_class,
        "create_safe_class_methods": transform_type_to_class_with_methods,
        "create_safe_method_decorator": transform_assignment_to_decorator,
        "create_safe_method_decorator_assignment": transform_decorator_to_assignment,
        "create_safe_next_guard": transform_next_default_to_try,
        "create_safe_next_default": transform_try_to_next_default,
        "create_safe_operator_call": transform_arithmetic_to_operator_call,
        "create_safe_arithmetic_expression": transform_operator_call_to_arithmetic,
        # Safe structural-pattern transforms (batch 2).
        "create_safe_explicit_exception": transform_suppress_to_try,
        "create_safe_exception_suppress": transform_try_to_suppress,
        "create_safe_keyword_call": transform_positional_to_keyword_call,
        "create_safe_positional_call": transform_keyword_to_positional_call,
        "create_safe_direct_attribute": transform_getattr_to_attribute,
        "create_safe_getattr_call": transform_attribute_to_getattr,
        # Safe, pattern-specific syntax families.
        "create_safe_set_comprehension": transform_for_add_to_set_comprehension,
        "create_safe_set_loop": transform_set_comprehension_to_for_add,
        "create_safe_lambda_expression": transform_def_to_lambda,
        "create_safe_lambda_function": transform_lambda_to_def,
        "create_safe_pattern_matching": transform_if_to_match,
        "create_safe_pattern_if": transform_match_to_if,
        "create_safe_local_annotation": transform_add_local_type_hints,
        "create_safe_local_deannotation": transform_remove_local_type_hints,
        # Existing iterations
        "create_direct_iteration": transform_to_direct_iteration_style,
        "create_index_iteration": transform_to_index_iteration_style,
        "create_while_iteration": transform_to_while_iteration_style,
        # New non-overlapping while-to-for feature
        "create_counted_while_to_for": transform_counted_while_to_for,
        # Existing collection actions remain available for other saved tags.
        "create_append_collection": transform_to_append_collection_style,
        "create_comprehension_collection": transform_to_comprehension_collection_style,
        "create_collection_style": transform_to_comprehension_collection_style,
        # Safe, explicit list <-> comprehension actions.
        "create_safe_append_collection": transform_list_comprehension_to_for_append,
        "create_safe_comprehension_collection": transform_for_append_to_list_comprehension,
        # Existing aggregation
        "create_aggregation_style": transform_to_sum_aggregation_style,
        "create_sum_aggregation": transform_to_sum_aggregation_style,
        "create_state_update_style": transform_to_loop_aggregation_style,
        # Existing dictionaries
        "create_mapping_style": transform_mapping_style,
        "create_dict_comprehension": transform_to_dict_comprehension_style,
        # Internal safe dictionary actions; public saved-tag mappings unchanged.
        "create_safe_dict_comprehension": transform_for_assignment_to_dict_comprehension,
        "create_safe_dict_loop": transform_dict_comprehension_to_for_assignment,
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
    try:
        after = transform_func(code)
    except Exception as error:
        result["status"] = "transformer_error"
        _add_unique(
            warnings,
            f"'{tag_name}' 변환기 실행 오류({type(error).__name__})로 "
            "이번 액션을 적용하지 않았습니다.",
        )
        return code, result
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
    applied_rules.append(f"적용 완료: {reason} 적용된 변환 액션: {action}")
    return after, result


def apply_coding_style(
    code: str,
    style: dict,
    function_cases: list[dict] | None = None,
    strict_runtime_validation: bool = False,
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

    # CAPSTONE_LARGE_CODE_SCOPES_V1: independent local plans for long Python files.
    # Preserve the existing whole-program actions, formatting pipeline and API.
    scoped_changes = False
    try:
        from app.services.style_large_code_service import apply_scoped_style_to_large_code
        locally_transformed, scoped_applied, scoped_warnings = apply_scoped_style_to_large_code(
            code=transformed_code,
            style=style,
            compare_style=compare_style_with_target_code,
            build_plan=build_transform_plan,
            get_transformer=_get_transform_function,
        )
        for note in scoped_warnings:
            _add_unique(warnings, note)
        if scoped_applied and locally_transformed != transformed_code:
            transformed_code = locally_transformed
            scoped_changes = True
            for item in scoped_applied:
                action_results.append({
                    "tag": item.get("tag", ""),
                    "action": item.get("action", ""),
                    "status": "applied",
                })
                applied_rules.append(
                    "적용 완료: 긴 코드의 " + item.get("scope", "함수")
                    + " 범위에 " + item.get("action", "") + " 변환"
                )
    except Exception as error:
        _add_unique(
            warnings,
            "긴 코드의 함수·메서드별 추가 변환 중 오류(" + type(error).__name__
            + ")가 발생하여 해당 추가 단계를 생략했습니다.",
        )

    if _normalize_code(code) == _normalize_code(transformed_code):
        transformed_code = code

    had_successful_transform = any(
        item.get("status") == "applied" for item in action_results
    )
    execution_verification = None
    transformation_cancelled_by_runtime = False

    if _is_changed(code, transformed_code) or function_cases is not None:
        # Preserve the public six-item return contract.  Never trust an
        # exception, a malformed response, or a contradictory verdict.
        verifier_malformed = False
        try:
            execution_verification = verify_execution_equivalence(
                original_code=code,
                transformed_code=transformed_code,
                function_cases=function_cases,
            )
        except Exception as error:
            verifier_malformed = True
            execution_verification = {
                "status": "not_verified",
                "equivalent": None,
                "message": f"검증기 실행 오류: {type(error).__name__}",
                "function_verification": None,
            }

        if not isinstance(execution_verification, dict):
            verifier_malformed = True
            execution_verification = {
                "status": "not_verified",
                "equivalent": None,
                "message": "검증기가 올바른 결과 형식을 반환하지 않았습니다.",
                "function_verification": None,
            }

        verification_status = execution_verification.get("status")
        equivalent = execution_verification.get("equivalent")
        verification_message = str(execution_verification.get("message") or "")
        if not isinstance(verification_status, str) or verification_status not in {"equivalent", "different", "not_verified"}:
            verifier_malformed = True
        if type(equivalent) not in (bool, type(None)):
            verifier_malformed = True
        if verification_status == "equivalent" and equivalent is not True:
            verifier_malformed = True
        if verification_status == "not_verified" and equivalent is not None:
            verifier_malformed = True

        if verifier_malformed:
            # A validator that cannot be trusted is not evidence of equality.
            execution_verification = {
                "status": "not_verified",
                "equivalent": None,
                "message": (
                    verification_message or "검증기의 결과가 불완전하거나 모순됩니다."
                ),
                "function_verification": None,
            }
            verification_status = "not_verified"
            equivalent = None

        changed = _is_changed(code, transformed_code)
        known_difference = (
            not verifier_malformed
            and (verification_status == "different" or equivalent is False)
        )
        must_rollback = changed and (
            known_difference
            or verifier_malformed
            or ((strict_runtime_validation or scoped_changes)
                and verification_status != "equivalent")
        )
        if must_rollback:
            transformation_cancelled_by_runtime = True
            transformed_code = code
            applied_rules.clear()
            # Do not leave reverted transformations labeled as successful.
            for item in action_results:
                if item.get("status") == "applied":
                    item["status"] = "rolled_back"
            if known_difference:
                note = (
                    "실행 결과 또는 함수 반환값의 차이가 확인되어 "
                    "전체 변환을 취소하고 원본을 유지했습니다. "
                )
            else:
                note = (
                    "실행 동등성이 검증되지 않아 전체 변환을 취소하고 "
                    "원본을 유지했습니다. "
                )
            _add_unique(warnings, note + verification_message)
        elif verification_status == "not_verified":
            _add_unique(
                warnings,
                "실행 동등성을 검증하지 못했습니다. 변환 결과는 검증되지 않은 "
                "코드이므로 적용 전 확인이 필요합니다. " + verification_message,
            )

    # A later action can undo an earlier action without a verifier rollback.
    # Report only transformations actually present in the final source.
    if not _is_changed(code, transformed_code) and had_successful_transform:
        applied_rules.clear()
        for item in action_results:
            if item.get("status") == "applied":
                item["status"] = "cancelled_net_zero"

    action_outcomes = summarize_action_outcomes(action_results)
    for note in format_cancelled_action_warnings(action_outcomes):
        _add_unique(warnings, note)

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
    elif transformation_cancelled_by_runtime:
        execution_summary = (
            "실행 동등성을 확인할 수 없어 전체 변환을 취소하고 원본 코드를 유지했습니다."
        )
    else:
        execution_summary = (
            "스타일 변환은 유지했지만 실행 결과 또는 "
            "함수 반환값의 동일성을 확인하지 못했습니다."
        )

    summary = (
        format_action_outcome_summary(action_outcomes) + " "
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
