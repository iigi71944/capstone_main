"""Build style-directed transformation plans without conflicting actions."""

from app.services.style_tag_transform_map_service import get_create_action_for_tag

FILTER_CONCEPT_TAG = "데이터 필터링 구조"
LIST_COMPREHENSION_TAG = "리스트 컴프리헨션"
SORT_CONCEPT_TAG = "정렬 중심 구조"
DICT_COMPREHENSION_TAG = "딕셔너리 컴프리헨션"
DICT_MAPPING_CONCEPT_TAG = "딕셔너리 기반 매핑 구조"
SAFE_DICT_ACTIONS = {"create_safe_dict_comprehension", "create_safe_dict_loop"}
FILTER_RELATED_COMPREHENSION_TAGS = {
    "리스트 컴프리헨션",
    "컴프리헨션 기반 간결 구조",
}

SAFE_LIST_ACTIONS = {
    "create_safe_append_collection",
    "create_safe_comprehension_collection",
}
LEGACY_LIST_ACTION_BY_SAFE = {
    "create_safe_append_collection": "create_append_collection",
    "create_safe_comprehension_collection": "create_comprehension_collection",
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
        action = item.get("action")
        # The same safe transformer may be selected by both a syntax and a
        # concept tag. Run it only once; leave other legacy dedup unchanged.
        key = ("safe_list", action) if action in SAFE_LIST_ACTIONS else (item.get("tag"), action)
        if key not in seen:
            seen.add(key)
            unique_actions.append(item)
    return unique_actions


def _resolve_collection_actions(actions: list[dict]) -> list[dict]:
    """Keep a single direction for each concrete list pattern preference.

    The explicit syntax/concept tags take precedence over broad legacy tags.
    Other existing transformations retain their relative order.
    """
    actions = _deduplicate_actions(actions)
    safe = {item.get("action") for item in actions} & SAFE_LIST_ACTIONS
    if len(safe) == 2:
        # A saved style can contain both list-building idioms in different
        # places. Without a per-function preference, do not guess a direction.
        # Preserve all unrelated actions.
        conflicting = SAFE_LIST_ACTIONS | set(LEGACY_LIST_ACTION_BY_SAFE.values())
        return [item for item in actions if item.get("action") not in conflicting]
    shadowed = {LEGACY_LIST_ACTION_BY_SAFE[name] for name in safe}
    kept = [item for item in actions if item.get("action") not in shadowed]
    return ([item for item in kept if item.get("action") in SAFE_LIST_ACTIONS]
            + [item for item in kept if item.get("action") not in SAFE_LIST_ACTIONS])


def _resolve_dictionary_actions(actions: list[dict]) -> list[dict]:
    """Prefer precise dictionary transforms without altering public tag names.

    An ambiguous two-direction plan fails closed for dictionary actions only.
    Broad non-dictionary actions keep their original order.
    """
    actions = _deduplicate_actions(actions)
    present = {item.get("action") for item in actions} & SAFE_DICT_ACTIONS
    if len(present) == 2:
        return [item for item in actions if item.get("action") not in SAFE_DICT_ACTIONS
                and not (item.get("tag") in {DICT_COMPREHENSION_TAG, DICT_MAPPING_CONCEPT_TAG}
                         and item.get("action") in {"create_dict_comprehension", "create_mapping_style"})]
    if "create_safe_dict_comprehension" in present:
        actions = [item for item in actions
                   if not (item.get("tag") == DICT_COMPREHENSION_TAG
                           and item.get("action") == "create_dict_comprehension")
                   and not (item.get("tag") == DICT_MAPPING_CONCEPT_TAG
                            and item.get("action") == "create_mapping_style")]
    if "create_safe_dict_loop" in present:
        actions = [item for item in actions
                   if not (item.get("tag") == DICT_MAPPING_CONCEPT_TAG
                           and item.get("action") == "create_mapping_style")]
    return ([item for item in actions if item.get("action") in SAFE_DICT_ACTIONS]
            + [item for item in actions if item.get("action") not in SAFE_DICT_ACTIONS])


# These operations rewrite the same for-loop family. When a saved style has
# inconsistent preferences, do not let the last action silently win.
_ITERATION_TARGET_ACTIONS = {
    "create_direct_iteration",
    "create_index_iteration",
    "create_while_iteration",
}
_ITERATION_FAMILY_ACTIONS = _ITERATION_TARGET_ACTIONS | {
    "create_counted_while_to_for",
}


def _resolve_iteration_actions(actions: list[dict]) -> list[dict]:
    """Deduplicate iteration targets and fail closed on conflicting targets.

    Counted while->for may accompany a direct/index for-loop preference:
    they operate on different original loop types. However, any request to
    turn for loops into while loops conflicts with either preference.
    """
    targets = {item.get("action") for item in actions} & _ITERATION_TARGET_ACTIONS
    has_counted_to_for = any(
        item.get("action") == "create_counted_while_to_for" for item in actions
    )
    conflicting = len(targets) > 1 or (
        "create_while_iteration" in targets and has_counted_to_for
    )
    if conflicting:
        return [
            item for item in actions
            if item.get("action") not in _ITERATION_FAMILY_ACTIONS
        ]

    result: list[dict] = []
    seen: set[str] = set()
    for item in actions:
        action = item.get("action")
        if action in _ITERATION_FAMILY_ACTIONS:
            if action in seen:
                continue
            seen.add(action)
        result.append(item)
    return result


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


def _prefer_dict_loop(diff: dict) -> bool:
    """Detect an explicit for/dictionary saved style vs a dictcomp target.

    Do not infer preference from the absence of the comprehension tag alone.
    A for-loop and a dictionary-related tag must occur in the saved style.
    """
    style_syntax = _get_tag_names(diff, "style_syntax_names")
    style_concept = _get_tag_names(diff, "style_concept_names")
    target_syntax = _get_tag_names(diff, "target_syntax_names")
    return (
        DICT_COMPREHENSION_TAG not in style_syntax
        and DICT_COMPREHENSION_TAG in target_syntax
        and "for문" in style_syntax
        and ("딕셔너리 리터럴" in style_syntax
             or DICT_MAPPING_CONCEPT_TAG in style_concept)
    )


def _build_dict_loop_action() -> dict:
    return {
        "tag": DICT_MAPPING_CONCEPT_TAG,
        "action": "create_safe_dict_loop",
        "reason": (
            "저장된 스타일은 for 반복문을 이용한 딕셔너리 누적 방식을 선호합니다. "
            "안전한 단일 제너레이터 딕셔너리 컴프리헨션만 반복문으로 변환합니다."
        ),
    }


def _build_filter_comprehension_action() -> dict:
    return {
        "tag": FILTER_CONCEPT_TAG,
        "action": "create_safe_comprehension_collection",
        "reason": (
            "저장된 스타일은 필터링된 리스트 컴프리헨션을 선호합니다. "
            "안전한 반복문과 append 패턴만 컴프리헨션으로 변환합니다."
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


_NEW_FAMILY_PAIRS = {
    "decorator": {"create_safe_method_decorator", "create_safe_method_decorator_assignment"},
    "guard": {"create_safe_next_guard", "create_safe_next_default"},
    "operator": {"create_safe_operator_call", "create_safe_arithmetic_expression"},
    "exception": {"create_safe_explicit_exception", "create_safe_exception_suppress"},
    "parameter": {"create_safe_keyword_call", "create_safe_positional_call"},
    "attribute": {"create_safe_direct_attribute", "create_safe_getattr_call"},
    "set": {"create_safe_set_comprehension", "create_safe_set_loop"},
    "lambda": {"create_safe_lambda_expression", "create_safe_lambda_function"},
    "pattern": {"create_safe_pattern_matching", "create_safe_pattern_if"},
    "annotation": {"create_safe_local_annotation", "create_safe_local_deannotation"},
}


def _resolve_new_family_actions(actions: list[dict]) -> list[dict]:
    """One direction per syntax family; remove duplicate concept/syntax action."""
    targets = {item.get("action") for item in actions}
    conflicting = set().union(*(
        family for family in _NEW_FAMILY_PAIRS.values() if len(family & targets) > 1
    ))
    result: list[dict] = []
    seen: set[str] = set()
    new_actions = set().union(*_NEW_FAMILY_PAIRS.values())
    for item in actions:
        action = item.get("action")
        if action in conflicting:
            continue
        if action in new_actions:
            if action in seen:
                continue
            seen.add(action)
        result.append(item)
    return result


def _explicit_reverse_actions(diff: dict) -> list[dict]:
    """Request a reverse transform only when a saved style explicitly
    contains a compatible target form. Missing tags alone are insufficient.
    """
    s = _get_tag_names(diff, "style_syntax_names")
    sc = _get_tag_names(diff, "style_concept_names")
    t = _get_tag_names(diff, "target_syntax_names")
    reverse = []
    if "for문" in s and "상태 변경 중심 구조" in sc and "세트 컴프리헨션" in t and "세트 컴프리헨션" not in s:
        reverse.append({"tag":"상태 변경 중심 구조", "action":"create_safe_set_loop", "reason":"저장 스타일은 for/set.add 누적 구조를 선호합니다."})
    if "함수 정의" in s and "lambda식" in t and "lambda식" not in s:
        reverse.append({"tag":"함수 정의", "action":"create_safe_lambda_function", "reason":"저장 스타일은 명시적 함수 정의를 선호합니다."})
    if "if문" in s and "패턴 매칭" in t and "패턴 매칭" not in s:
        reverse.append({"tag":"if문", "action":"create_safe_pattern_if", "reason":"저장 스타일은 조건문 분기 형태를 선호합니다."})
    return reverse


def build_transform_plan(diff: dict) -> dict:
    missing_syntax_tags = diff.get("missing_syntax_tags", [])
    missing_concept_tags = diff.get("missing_concept_tags", [])
    actions: list[dict] = _explicit_reverse_actions(diff)
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

    prefer_dict_loop = _prefer_dict_loop(diff)
    if prefer_dict_loop:
        actions.append(_build_dict_loop_action())

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

        # Keep the historical public tag mapping unchanged (needed by
        # existing tests and saved styles), but select the safe implementation
        # at plan time for these two explicit list preferences only.
        if tag_name == "리스트 누적 방식 사용":
            action = "create_safe_append_collection"
        elif tag_name == LIST_COMPREHENSION_TAG:
            action = "create_safe_comprehension_collection"
        elif tag_name == DICT_COMPREHENSION_TAG:
            # Public mapping remains create_dict_comprehension for compatibility.
            action = "create_safe_dict_comprehension"

        # A loop-centric concept alone does not determine whether to generate
        # for or while. Do not run the new action without an explicit preference.
        if action == "create_counted_while_to_for":
            if not prefer_for:
                compare_only.append(tag_name)
            continue

        if (
            prefer_filter
            and action in {"create_comprehension_collection", "create_safe_comprehension_collection"}
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
        "actions": _resolve_new_family_actions(_resolve_iteration_actions(
            _resolve_dictionary_actions(_resolve_collection_actions(actions))
        )),
        "compare_only": sorted(set(compare_only)),
    }
