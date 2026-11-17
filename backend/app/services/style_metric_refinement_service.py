"""Batch 35-5: evidence-backed preferences and conservative closed-pattern gates.

Only version-1 *complete* 81-metric snapshots opt into these extra decisions.
Legacy styles retain their existing behavior. This module never executes code,
changes a public tag name, or edits an existing transformer. All decisions use
observed integer counters; missing values are not silently treated as zeros.
"""
from __future__ import annotations

from typing import Any


_DIRECTIONS = (
    # (tag, preferred metric, opposite metric, family metric, action)
    ("sorted 사용", "sorted_reverse_false_explicit_count",
     "sorted_reverse_false_implicit_count", "sorted_call_count",
     "create_safe_explicit_sorted_reverse"),
    ("sorted 사용", "sorted_reverse_false_implicit_count",
     "sorted_reverse_false_explicit_count", "sorted_call_count",
     "create_safe_implicit_sorted_reverse"),
    ("문자열 메서드 호출", "strip_none_explicit_count",
     "strip_none_implicit_count", "string_strip_call_count",
     "create_safe_explicit_strip_default"),
    ("문자열 메서드 호출", "strip_none_implicit_count",
     "strip_none_explicit_count", "string_strip_call_count",
     "create_safe_implicit_strip_default"),
)

# (metric, relation, threshold): target-only evidence matching the *existing*
# tiny, closed-module transformer. The transformer still checks the real AST.
_BASE_CLOSED = (
    ("function_count", "eq", 1),
    ("class_count", "eq", 0),
    ("print_call_count", "ge", 1),
)
_PARAM_CLOSED = _BASE_CLOSED + (
    ("async_function_count", "eq", 0),
    ("return_count", "eq", 1),
    ("default_param_count", "eq", 0),
    ("vararg_count", "eq", 0),
    ("kwarg_count", "eq", 0),
    ("parameter_using_function_count", "eq", 1),
    ("call_count", "ge", 2),
)
_CLOSED_RULES = {
    "create_safe_closed_default_parameter": _PARAM_CLOSED + (
        ("function_parameter_count", "eq", 1),
        ("used_function_parameter_count", "eq", 1),
        ("positional_arg_count", "ge", 2),
    ),
    "create_safe_closed_varargs": _PARAM_CLOSED + (
        ("function_parameter_count", "eq", 2),
        ("used_function_parameter_count", "eq", 2),
        ("keyword_arg_count", "eq", 0),
        ("positional_arg_count", "ge", 3),
    ),
    "create_safe_closed_kwargs": _PARAM_CLOSED + (
        ("function_parameter_count", "eq", 2),
        ("used_function_parameter_count", "eq", 2),
        ("keyword_arg_count", "ge", 2),
    ),
    "create_safe_closed_async_definition": _BASE_CLOSED + (
        ("async_function_count", "eq", 0),
        ("import_count", "eq", 1),
        ("function_parameter_count", "eq", 0),
        ("return_count", "eq", 1),
        ("call_count", "ge", 2),
    ),
    "create_safe_closed_await": _BASE_CLOSED + (
        ("async_function_count", "eq", 1),
        ("import_count", "eq", 1),
        ("function_parameter_count", "eq", 0),
        ("await_count", "eq", 0),
        ("return_count", "eq", 1),
        ("call_count", "ge", 3),
    ),
    "create_safe_closed_async_structure": _BASE_CLOSED + (
        ("async_function_count", "eq", 1),
        ("import_count", "eq", 1),
        ("function_parameter_count", "eq", 0),
        ("await_count", "eq", 0),
        ("return_count", "eq", 1),
        ("call_count", "ge", 3),
    ),
    "create_safe_closed_long_function": _BASE_CLOSED + (
        ("async_function_count", "eq", 0),
        ("function_parameter_count", "eq", 0),
        ("loop_count", "eq", 1),
        ("return_count", "eq", 0),
        ("max_function_body_length", "eq", 1),
        ("call_count", "ge", 2),
    ),
}


def _count(metrics: dict, name: str) -> int | None:
    if not isinstance(metrics, dict):
        return None
    value = metrics.get(name)
    return value if type(value) is int and value >= 0 else None


def _current_snapshot(diff: dict) -> bool:
    if not isinstance(diff, dict):
        return False
    info = diff.get("style_metrics_info")
    return (isinstance(info, dict)
            and info.get("status") == "current_complete"
            and info.get("stored_version") == 1
            and info.get("automatic_transforms_allowed") is True)


def _evidence(diff: dict) -> tuple[dict, dict]:
    saved = diff.get("style_metrics", {})
    analysis = diff.get("target_analysis", {})
    target = analysis.get("metrics", {}) if isinstance(analysis, dict) else {}
    return saved if isinstance(saved, dict) else {}, target if isinstance(target, dict) else {}


def add_dominant_default_actions(diff: dict, actions: list[dict]) -> list[dict]:
    """Enable strongly preferred default-argument forms in mixed styles.

    Prior logic only recognized a 100%-one-sided preference. A 3:1 (or more
    decisive) observed preference is actionable, but a tie/weak 2:1 is not.
    Strict AST transformers still decide whether any actual edit is safe.
    """
    result = list(actions)
    if not _current_snapshot(diff):
        return result
    saved, target = _evidence(diff)
    for tag, preferred, opposite, family, action in _DIRECTIONS:
        s_pref = _count(saved, preferred)
        s_opp = _count(saved, opposite)
        s_family = _count(saved, family)
        t_pref = _count(target, preferred)
        t_opp = _count(target, opposite)
        t_family = _count(target, family)
        if any(x.get("action") == action for x in result if isinstance(x, dict)):
            continue
        # Only the previously unsupported mixed-preference case gets added.
        # Demand a substantial majority, an available opposite candidate,
        # and no target occurrence of the already-preferred surface form.
        if (None not in (s_pref, s_opp, s_family, t_pref, t_opp, t_family)
                and s_pref >= 3 and s_opp >= 1
                and s_pref >= 2 * s_opp + 1
                and s_family >= s_pref + s_opp
                and t_pref == 0 and t_opp >= 1 and t_family >= t_opp):
            result.append({
                "tag": tag, "action": action,
                "reason": (
                    "저장된 메트릭에서 같은 메서드의 기본 인자 표현이 "
                    f"{s_pref}:{s_opp}로 우세하고, 대상 코드에서 반대 표현 "
                    f"{t_opp}건이 확인되어 해당 안전 변환을 시도합니다."
                ),
            })
    return result


def refine_closed_pattern_actions(diff: dict, actions: list[dict]) -> tuple[list[dict], list[dict]]:
    """Fail closed before attempting seven narrow structural transforms.

    Never reorder survivors or modify inputs. Record which observed counts
    prevented attempting an action as a Batch35-3 omitted-action diagnostic.
    """
    if not _current_snapshot(diff):
        return list(actions), []
    _, target = _evidence(diff)
    selected = []
    omitted = []
    for item in actions:
        if not isinstance(item, dict):
            selected.append(item)
            continue
        action = item.get("action")
        conditions = _CLOSED_RULES.get(action)
        if conditions is None:
            selected.append(item)
            continue
        failed = []
        for metric, relation, expected in conditions:
            actual = _count(target, metric)
            matches = actual is not None and (
                (actual == expected) if relation == "eq" else (actual >= expected)
            )
            if not matches:
                failed.append({
                    "metric": metric, "operator": relation,
                    "expected": expected, "actual": actual,
                })
        if not failed:
            selected.append(item)
            continue
        omitted.append({
            "tag": item.get("tag") if isinstance(item.get("tag"), str) else "",
            "action": action,
            "status": "omitted", "stage": "metric_evidence_35_5",
            "reason_code": "target_metric_shape_mismatch",
            "reason": (
                "대상 코드의 81개 메트릭 중 함수·인자·호출 구조가 "
                "변환기의 제한된 안전 패턴과 맞지 않아 실행을 생략했습니다."
            ),
            "failed_conditions": failed,
        })
    return selected, omitted


__all__ = ["add_dominant_default_actions", "refine_closed_pattern_actions"]
