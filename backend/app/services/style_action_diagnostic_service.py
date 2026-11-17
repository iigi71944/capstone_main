"""Batch 35-3: record *why* a planned style action was excluded or not applied.

Observation only: no transformer is run here and this module never decides which
transformation to execute. The recorded reasons are conservative explanations
of existing plan filtering and final action statuses, not semantic proofs.
"""
from __future__ import annotations

from collections import Counter


_STAGE_REASON = {
    "policy_initial": (
        "shared_policy_deduplicated",
        "문법·개념 태그가 같은 변환 엔진 정책을 공유하여 우선순위에 따라 한 액션만 남겼습니다.",
    ),
    "collection": (
        "collection_preference_conflict",
        "리스트 생성 방식의 선호가 충돌하거나 더 구체적인 안전 변환이 선택되어 제외했습니다.",
    ),
    "dictionary": (
        "dictionary_preference_conflict",
        "딕셔너리 변환 방향이 충돌하거나 안전 변환이 우선되어 제외했습니다.",
    ),
    "iteration": (
        "iteration_preference_conflict",
        "반복문 방향이 서로 충돌하여 해당 반복문 계열 액션을 제외했습니다.",
    ),
    "bidirectional_families": (
        "bidirectional_family_conflict",
        "같은 문법 계열에서 양방향 변환 요청이 충돌하여 제외했습니다.",
    ),
    "policy_final": (
        "shared_policy_deduplicated",
        "문법·개념 태그의 공통 엔진 중복 실행을 방지하기 위해 제외했습니다.",
    ),
}

_STATUS_REASON = {
    "applied": ("applied", "변환 액션이 적용되었으며 최종 취소되지 않았습니다."),
    "no_safe_pattern": ("no_safe_pattern", "대상 코드에서 변환기의 안전 조건을 만족하는 패턴을 찾지 못했습니다."),
    "skipped_shape_preflight": ("missing_required_ast_shape", "필수 AST 구조가 없어 변환기를 호출하지 않았습니다."),  # CAPSTONE_BATCH36_3_DIAG_V1
    "transformer_missing": ("transformer_missing", "해당 액션과 연결된 변환기가 없습니다."),
    "transformer_error": ("transformer_error", "변환기를 실행하는 중 예외가 발생했습니다."),
    "empty_result": ("empty_result", "변환기가 유효한 코드 문자열을 반환하지 않았습니다."),
    "invalid_result": ("invalid_python", "변환 결과의 Python 문법을 검증하지 못했습니다."),
    "cancelled_net_zero": ("cancelled_by_later_action", "후속 액션이 앞선 변경을 되돌려 최종 코드에 반영되지 않았습니다."),
    "rolled_back": ("runtime_rollback", "실행 동등성 검증에 따른 전체 롤백으로 적용되지 않았습니다."),
}


def _identity(item: dict) -> tuple[str, str]:
    tag = item.get("tag")
    action = item.get("action")
    return (tag if isinstance(tag, str) else "", action if isinstance(action, str) else "")


def trace_plan_filter(before: list[dict], after: list[dict], stage: str) -> list[dict]:
    """Describe items removed by an existing resolver; never change its result.

    Multiset subtraction handles duplicate tags/actions and arbitrary reorderings.
    Metadata added by policy finalization is intentionally ignored for identity.
    """
    if stage not in _STAGE_REASON:
        raise ValueError("Unknown transformation plan stage: " + str(stage))
    survivors = Counter(_identity(item) for item in after if isinstance(item, dict))
    remaining_actions = {item.get("action") for item in after if isinstance(item, dict)}
    original_actions = [item.get("action") for item in before if isinstance(item, dict)]
    omitted = []
    for item in before:
        if not isinstance(item, dict):
            continue
        key = _identity(item)
        if survivors[key] > 0:
            survivors[key] -= 1
            continue
        code, reason = _STAGE_REASON[stage]
        action = key[1]
        if action in remaining_actions:
            code = "duplicate_action"
            reason = "같은 변환 액션이 이미 계획에 포함되어 중복 실행을 생략했습니다."
        elif stage == "collection":
            has_both = {"create_safe_append_collection", "create_safe_comprehension_collection"}.issubset(original_actions)
            if not has_both:
                code = "superseded_by_safe_action"
                reason = "기존 리스트 변환보다 구체적인 안전 변환이 우선되어 생략했습니다."
        elif stage == "dictionary":
            has_both = {"create_safe_dict_comprehension", "create_safe_dict_loop"}.issubset(original_actions)
            if not has_both:
                code = "superseded_by_safe_action"
                reason = "기존 딕셔너리 변환보다 구체적인 안전 변환이 우선되어 생략했습니다."
        omitted.append({
            "tag": key[0], "action": action, "status": "omitted",
            "stage": stage, "reason_code": code, "reason": reason,
        })
    return omitted


def _attempt_result(raw: dict, verification: dict | None) -> dict:
    tag, action = _identity(raw)
    status = raw.get("status")
    status = status if isinstance(status, str) else "unknown"
    reason_code, reason = _STATUS_REASON.get(
        status, ("unknown_status", "변환 액션의 처리 상태를 확인하지 못했습니다.")
    )
    if status == "rolled_back" and isinstance(verification, dict):
        if verification.get("status") == "different" or verification.get("equivalent") is False:
            reason_code = "runtime_difference"
            reason = "변환 전후 실행 결과 또는 함수 검증 결과가 달라 전체 변환을 취소했습니다."
        else:
            reason_code = "runtime_unverified"
            reason = "실행 결과의 동일성이 검증되지 않아 전체 변환을 취소했습니다."
    if status == "skipped_shape_preflight":
        reason_code = raw.get("preflight_reason_code") or reason_code
        reason = raw.get("preflight_reason") or reason
    result = {
        "tag": tag, "action": action, "status": status,
        "reason_code": reason_code, "reason": reason,
    }
    plan_reason = raw.get("plan_reason")
    if isinstance(plan_reason, str) and plan_reason:
        result["plan_reason"] = plan_reason
    for key in ("policy_action", "policy_family", "policy_role", "policy_source_tags"):
        if key in raw:
            result[key] = raw[key]
    return result


def build_transform_diagnostics(
    plan: dict, results: list[dict], verification: dict | None = None
) -> dict:
    """One JSON-compatible record for plan omissions, attempts, compare-only tags.

    This is attached as an additive field in final_diff. It does not modify
    the legacy six-element apply result, action selection, or status counting.
    """
    planned_omissions = plan.get("omitted_actions", []) if isinstance(plan, dict) else []
    omitted = [dict(x) for x in planned_omissions if isinstance(x, dict)]
    attempted = [_attempt_result(x, verification) for x in results if isinstance(x, dict)]
    raw_unselected = plan.get("not_selected_tags", []) if isinstance(plan, dict) else []
    not_selected = [dict(x) for x in raw_unselected if isinstance(x, dict)]
    compare_only = []
    tags = plan.get("compare_only", []) if isinstance(plan, dict) else []
    raw_details = plan.get("compare_only_details", []) if isinstance(plan, dict) else []
    details_by_tag = {
        row["tag"]: row for row in raw_details
        if isinstance(row, dict) and isinstance(row.get("tag"), str)
    }
    for tag in tags:
        if not isinstance(tag, str) or not tag:
            continue
        detail = details_by_tag.get(tag, {})
        reason_code = detail.get("reason_code")
        reason = detail.get("reason")
        compare_only.append({
            "tag": tag,
            "status": "compare_only",
            "reason_code": reason_code if isinstance(reason_code, str) else "compare_only_no_selected_action",
            "reason": reason if isinstance(reason, str) else
                      "현재 저장 스타일의 태그와 변환 조건으로는 실행할 액션을 선택하지 않아 비교에만 사용했습니다.",
        })
    return {
        "version": 1,
        "omitted_actions": omitted,
        "attempted_actions": attempted,
        "compare_only_tags": compare_only,
        "not_selected_tags": not_selected,
        "counts": {
            "omitted": len(omitted),
            "attempted": len(attempted),
            "not_applied": sum(x["status"] != "applied" for x in attempted),
            "compare_only": len(compare_only),
            "not_selected": len(not_selected),
        },
    }
