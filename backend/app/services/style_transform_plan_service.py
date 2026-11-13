"""Build style-directed transformation plans without conflicting actions."""

from app.services.style_tag_transform_map_service import get_create_action_for_tag

FILTER_CONCEPT_TAG = "데이터 필터링 구조"
LIST_COMPREHENSION_TAG = "리스트 컴프리헨션"
SORT_CONCEPT_TAG = "정렬 중심 구조"
FILTER_RELATED_COMPREHENSION_TAGS = {
    "리스트 컴프리헨션",
    "컴프리헨션 기반 간결 구조",
}


def _get_tag_name(tag_item: dict) -> str:
    if not isinstance(tag_item, dict):
        return ""
    tag_name = tag_item.get("tag", "")
    return tag_name if isinstance(tag_name, str) else ""


def _deduplicate_actions(actions: list[dict]) -> list[dict]:
    unique_actions = []
    seen = set()
    for item in actions:
        key = (item.get("tag"), item.get("action"))
        if key not in seen:
            seen.add(key)
            unique_actions.append(item)
    return unique_actions


def _get_tag_names(diff: dict, key: str) -> set[str]:
    values = diff.get(key)
    if not isinstance(values, (set, list, tuple)):
        return set()
    return {value for value in values if isinstance(value, str)}


def _get_style_metrics(diff: dict) -> dict:
    metrics = diff.get("style_metrics", {})
    return metrics if isinstance(metrics, dict) else {}


def _get_target_metrics(diff: dict) -> dict:
    analysis = diff.get("target_analysis", {})
    if not isinstance(analysis, dict):
        return {}
    metrics = analysis.get("metrics", {})
    return metrics if isinstance(metrics, dict) else {}


def _metric_count(metrics: dict, key: str) -> int:
    value = metrics.get(key, 0)
    if type(value) is not int:
        return 0
    return max(value, 0)


def _prefer_filtered_comprehension(diff: dict) -> bool:
    if get_create_action_for_tag(FILTER_CONCEPT_TAG) != "create_filter_style":
        return False
    style_syntax = _get_tag_names(diff, "style_syntax_names")
    style_concept = _get_tag_names(diff, "style_concept_names")
    target_syntax = _get_tag_names(diff, "target_syntax_names")
    target_concept = _get_tag_names(diff, "target_concept_names")
    target_metrics = _get_target_metrics(diff)
    return (
        FILTER_CONCEPT_TAG in style_concept
        and LIST_COMPREHENSION_TAG in style_syntax
        and FILTER_CONCEPT_TAG in target_concept
        and LIST_COMPREHENSION_TAG not in target_syntax
        and "for문" in target_syntax
        and _metric_count(target_metrics, "append_call_count") >= 1
        and _metric_count(target_metrics, "filter_pattern_count") >= 1
    )


def _prefer_sorted_style(diff: dict) -> bool:
    if get_create_action_for_tag(SORT_CONCEPT_TAG) != "create_sort_style":
        return False
    style_concept = _get_tag_names(diff, "style_concept_names")
    target_concept = _get_tag_names(diff, "target_concept_names")
    if SORT_CONCEPT_TAG not in style_concept or SORT_CONCEPT_TAG not in target_concept:
        return False
    style_metrics = _get_style_metrics(diff)
    target_metrics = _get_target_metrics(diff)
    return (
        _metric_count(style_metrics, "sorted_call_count") >= 1
        and _metric_count(style_metrics, "sort_method_call_count") == 0
        and _metric_count(target_metrics, "sort_method_call_count") >= 1
        and _metric_count(target_metrics, "sorted_call_count") == 0
    )


def _condition_preference(diff: dict) -> str | None:
    style = _get_style_metrics(diff)
    target = _get_target_metrics(diff)
    style_if = _metric_count(style, "if_count")
    style_ternary = _metric_count(style, "if_exp_count")
    target_if = _metric_count(target, "if_count")
    target_ternary = _metric_count(target, "if_exp_count")
    if style_if > target_if and style_ternary == 0 and target_ternary >= 1:
        return "if"
    if style_ternary > target_ternary and style_if == 0 and target_if >= 1:
        return "expression"
    return None


def _prefer_direct_boolean_return(diff: dict, condition_preference: str | None) -> bool:
    if condition_preference is not None:
        return False
    style = _get_style_metrics(diff)
    target = _get_target_metrics(diff)
    return (
        _metric_count(style, "return_count") == 1
        and _metric_count(style, "if_count") == 0
        and _metric_count(style, "if_exp_count") == 0
        and _metric_count(target, "return_count") >= 2
        and _metric_count(target, "if_count") >= 1
    )


def _prefer_counted_while_to_for(diff: dict) -> bool:
    """Style prefers for-only; target contains while. Unlike the existing
    iteration transformers this action touches only ast.While statements.
    """
    style_syntax = _get_tag_names(diff, "style_syntax_names")
    target_syntax = _get_tag_names(diff, "target_syntax_names")
    return (
        get_create_action_for_tag("반복문 중심 구조") == "create_counted_while_to_for"
        and "for문" in style_syntax
        and "while문" not in style_syntax
        and "while문" in target_syntax
    )


def _build_filter_comprehension_action() -> dict:
    return {
        "tag": FILTER_CONCEPT_TAG,
        "action": "create_filter_style",
        "reason": (
            "저장된 스타일은 리스트 컴프리헨션으로 필터링하고 대상 코드는 "
            "반복문과 append를 사용하여 안전한 패턴을 변환합니다."
        ),
    }


def _build_sorted_style_action() -> dict:
    return {
        "tag": SORT_CONCEPT_TAG,
        "action": "create_sort_style",
        "reason": (
            "저장된 스타일은 sorted()를 사용하지만 대상 코드는 "
            "list.sort()를 사용하여 안전한 패턴을 변환합니다."
        ),
    }


def _build_condition_action(preference: str) -> dict:
    if preference == "if":
        return {
            "tag": "if문",
            "action": "create_if_statement",
            "reason": (
                "저장된 스타일은 if문 중심이고 대상 코드는 삼항 조건식을 "
                "사용하므로 단순 대입/반환 구문을 if/else로 전환합니다."
            ),
        }
    return {
        "tag": "삼항 조건식",
        "action": "create_conditional_expression",
        "reason": (
            "저장된 스타일은 삼항 조건식을 사용하고 대상 코드는 "
            "if/else를 사용하므로 단순 대입/반환 구문을 전환합니다."
        ),
    }


def _build_boolean_return_action() -> dict:
    return {
        "tag": "return문",
        "action": "create_return_structure",
        "reason": (
            "저장된 스타일은 한 번의 직접 반환을 선호하여 "
            "참·거짓을 분기하는 안전한 패턴만 단일 return으로 변환합니다."
        ),
    }


def _build_counted_while_to_for_action() -> dict:
    return {
        "tag": "반복문 중심 구조",
        "action": "create_counted_while_to_for",
        "reason": (
            "저장된 스타일은 for 반복을 사용하고 while 반복은 사용하지 "
            "않습니다. 정수 증감이 명확한 while만 for/range로 변환합니다."
        ),
    }


def build_transform_plan(diff: dict) -> dict:
    missing_syntax_tags = diff.get("missing_syntax_tags", [])
    missing_concept_tags = diff.get("missing_concept_tags", [])
    actions: list[dict] = []
    compare_only: list[str] = []

    prefer_filter = _prefer_filtered_comprehension(diff)
    if prefer_filter:
        actions.append(_build_filter_comprehension_action())

    prefer_sort = _prefer_sorted_style(diff)
    if prefer_sort:
        actions.append(_build_sorted_style_action())

    # Run before ordinary iteration actions. The latter act only on for-loops.
    prefer_for = _prefer_counted_while_to_for(diff)
    if prefer_for:
        actions.append(_build_counted_while_to_for_action())

    condition_preference = _condition_preference(diff)
    if condition_preference is not None:
        actions.append(_build_condition_action(condition_preference))

    prefer_return = _prefer_direct_boolean_return(diff, condition_preference)
    if prefer_return:
        actions.append(_build_boolean_return_action())

    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:
        tag_name = _get_tag_name(tag_item)
        if not tag_name:
            continue
        action = get_create_action_for_tag(tag_name)
        if action is None:
            compare_only.append(tag_name)
            continue

        # A loop-centric concept alone does not determine whether to generate
        # for or while. Do not run the new action without an explicit preference.
        if action == "create_counted_while_to_for":
            if not prefer_for:
                compare_only.append(tag_name)
            continue

        if (
            prefer_filter
            and action == "create_comprehension_collection"
            and tag_name in FILTER_RELATED_COMPREHENSION_TAGS
        ):
            continue
        if prefer_sort and action == "create_sort_style":
            continue
        if condition_preference == "if" and action == "create_if_statement":
            continue
        if condition_preference == "expression" and action == "create_conditional_expression":
            continue
        if prefer_return and action == "create_return_structure":
            continue
        if condition_preference == "if" and action == "create_conditional_expression":
            continue
        if condition_preference == "expression" and action == "create_if_statement":
            continue

        actions.append({
            "tag": tag_name,
            "action": action,
            "reason": (
                f"저장된 코딩 스타일에는 '{tag_name}' 태그가 있지만 "
                "대상 코드에는 없으므로 해당 스타일 반영을 시도합니다."
            ),
        })

    return {
        "actions": _deduplicate_actions(actions),
        "compare_only": sorted(set(compare_only)),
    }
