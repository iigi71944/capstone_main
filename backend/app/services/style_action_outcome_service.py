"""User-facing summary of the saved-style *action attempts*.

This module does not run user code and does not claim semantic equivalence.
Its counts describe the final outcome of planned transformation actions;
'changed' is not interchangeable with 'runtime verified'.
"""

from __future__ import annotations

from collections import Counter

_STATUS = {
    "applied": ("applied", "적용"),
    "rolled_back": ("cancelled", "실행 검증 후 취소"),
    "cancelled_net_zero": ("cancelled", "후속 변환으로 최종 변경 취소"),
    "no_safe_pattern": ("skipped", "적용할 안전한 코드 패턴 없음"),
    "transformer_missing": ("skipped", "연결된 변환기 없음"),
    "transformer_error": ("skipped", "변환기 실행 오류"),
    "invalid_result": ("skipped", "변환 후 문법 오류"),
    "empty_result": ("skipped", "유효한 변환 결과 없음"),
}


def summarize_action_outcomes(results: list[dict] | None) -> dict:
    """Return stable, JSON-compatible final attempt outcomes in plan order."""
    items = []
    for raw in results or []:
        if not isinstance(raw, dict):
            continue
        status = raw.get("status")
        category, label = _STATUS.get(status, ("skipped", "알 수 없는 처리 결과"))
        tag = raw.get("tag")
        action = raw.get("action")
        items.append({
            "tag": tag if isinstance(tag, str) else "",
            "action": action if isinstance(action, str) else "",
            "status": status if isinstance(status, str) else "unknown",
            "category": category,
            "label": label,
        })
    counts = Counter(item["category"] for item in items)
    return {
        "total": len(items),
        "applied": counts["applied"],
        "skipped": counts["skipped"],
        "cancelled": counts["cancelled"],
        "items": items,
    }


def format_action_outcome_summary(report: dict) -> str:
    """Count actions, not tags or verified code lines."""
    if report["total"] == 0:
        return "자동 변환 계획에 실행할 액션이 없습니다."
    return (
        f"자동 변환 액션 {report['total']}건: "
        f"적용 {report['applied']}건, "
        f"생략 {report['skipped']}건, "
        f"취소 {report['cancelled']}건."
    )


def format_cancelled_action_warnings(report: dict) -> list[str]:
    """Surface actions that were attempted but did not survive the final result."""
    notes = []
    for item in report["items"]:
        if item["category"] != "cancelled":
            continue
        name = item["tag"] or item["action"] or "이름 없는 액션"
        notes.append(f"변환 취소: '{name}' — {item['label']}. 최종 코드에 적용되지 않았습니다.")
    return notes
