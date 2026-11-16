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
    # CAPSTONE_BATCH22_ASSERT_RAISE_CONFLICT_V1
    "assert_raise": {"create_safe_debug_assert", "create_safe_debug_raise"},
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

    # CAPSTONE_UNMAPPED_BATCH3_V1: style syntax list stays at 19 entries.
    # Two omitted syntax preferences are inferred from the stored metrics.
    # Avoid adding generated syntax merely because a tag exists in the registry.
    saved_metrics = _get_style_metrics(diff)
    current_metrics = _get_target_metrics(diff)
    if (_metric_count(saved_metrics, "aug_assign_count") > 0
            and _metric_count(current_metrics, "aug_assign_count") == 0):
        actions.append({
            "tag": "복합 할당",
            "action": "create_safe_augmented_assignment",
            "reason": "저장 스타일의 복합 할당 선호도가 관측되어 정수 리터럴 누적 대입에 한정해 적용합니다.",
        })
    if (_metric_count(saved_metrics, "dict_method_call_count") > 0
            and _metric_count(current_metrics, "dict_method_call_count") == 0
            and "딕셔너리 기반 매핑 구조" in _get_tag_names(diff, "style_concept_names")):
        actions.append({
            "tag": "딕셔너리 메서드 호출",
            "action": "create_safe_dict_get",
            "reason": "저장 스타일의 딕셔너리 메서드 선호도가 관측되어 확정된 키 조회에만 적용합니다.",
        })

    # CAPSTONE_UNMAPPED_BATCH4_V1: no changes to the 19-item syntax storage filter.
    # Existing metrics provide evidence for literal preferences. Avoid creating
    # missing tags blindly: only supported constant constructors are rewritten.
    saved_metrics_b4 = _get_style_metrics(diff)
    target_metrics_b4 = _get_target_metrics(diff)
    for tag_b4, metric_b4, action_b4 in (
        ("리스트 리터럴", "list_literal_count", "create_safe_list_literal"),
        ("딕셔너리 리터럴", "dict_literal_count", "create_safe_dict_literal"),
        ("튜플 리터럴", "tuple_literal_count", "create_safe_tuple_literal"),
    ):
        if (_metric_count(saved_metrics_b4, metric_b4) > 0
                and _metric_count(target_metrics_b4, metric_b4) == 0):
            actions.append({
                "tag": tag_b4,
                "action": action_b4,
                "reason": "저장 스타일에서 관측한 리터럴 표현을 동등성이 검토된 생성자 패턴에 적용합니다.",
            })

    # CAPSTONE_UNMAPPED_BATCH5_V1: 19 syntax tags in stored styles remain unchanged.
    # Detect four new syntax preferences from metrics that were *already*
    # stored by previous versions. Require evidence in the saved style and a
    # matching absence/presence in the target before considering safe edits.
    saved_metrics_b5 = _get_style_metrics(diff)
    target_metrics_b5 = _get_target_metrics(diff)
    if (_metric_count(saved_metrics_b5, "subscript_count") > 0
            and _metric_count(target_metrics_b5, "subscript_count") == 0):
        actions.append({
            "tag": "인덱싱 사용",
            "action": "create_safe_known_key_indexing",
            "reason": "저장된 스타일의 인덱싱 선호도를 확인하여 확정된 딕셔너리 키 조회에만 적용합니다.",
        })
    if (_metric_count(saved_metrics_b5, "attribute_count") > 0
            and _metric_count(target_metrics_b5, "attribute_count") == 0):
        actions.append({
            "tag": "속성 접근",
            "action": "create_safe_direct_attribute",
            "reason": "저장된 스타일의 직접 속성 접근 선호도를 확인하여 안전한 getattr 표현만 변경합니다.",
        })
    if (_metric_count(saved_metrics_b5, "keyword_arg_count") > 0
            and _metric_count(target_metrics_b5, "keyword_arg_count") == 0):
        actions.append({
            "tag": "키워드 인자 사용",
            "action": "create_safe_keyword_call",
            "reason": "저장된 스타일의 키워드 인자 선호도를 확인하여 정적인 함수 호출만 변경합니다.",
        })
    elif (_metric_count(saved_metrics_b5, "keyword_arg_count") == 0
            and _metric_count(saved_metrics_b5, "positional_arg_count") > 0
            and _metric_count(target_metrics_b5, "keyword_arg_count") > 0):
        actions.append({
            "tag": "위치 인자 사용",
            "action": "create_safe_positional_call",
            "reason": "저장된 스타일의 위치 인자 선호도를 확인하여 순서가 보존되는 함수 호출만 변경합니다.",
        })

    # CAPSTONE_UNMAPPED_BATCH9_V1: infer syntax preferences exclusively from
    # already-persisted metric counters; DO NOT expand the 19 stored syntax tags.
    saved_metrics_b9 = _get_style_metrics(diff)
    target_metrics_b9 = _get_target_metrics(diff)
    for tag_b9, metric_b9, action_b9 in (
        ("range 사용", "range_call_count", "create_safe_literal_range"),
        ("논리 연산", "bool_op_count", "create_safe_nested_boolean"),
        ("멤버십 연산", "membership_op_count", "create_safe_known_membership"),
    ):
        if (_metric_count(saved_metrics_b9, metric_b9) > 0
                and _metric_count(target_metrics_b9, metric_b9) == 0):
            actions.append({
                "tag": tag_b9,
                "action": action_b9,
                "reason": "저장된 스타일의 기존 메트릭 선호를 확인하여 제한된 안전 패턴만 변환합니다.",
            })
    if (_metric_count(saved_metrics_b9, "sorted_call_count") > 0
            and _metric_count(saved_metrics_b9, "sort_method_call_count") == 0
            and _metric_count(target_metrics_b9, "sorted_call_count") == 0
            and _metric_count(target_metrics_b9, "sort_method_call_count") > 0
            and not any(item.get("action") == "create_sort_style" for item in actions)):
        actions.append({
            "tag": "sorted 사용",
            "action": "create_sort_style",
            "reason": "저장된 스타일의 sorted() 호출 선호와 대상 코드의 list.sort()를 비교하여 변환합니다.",
        })

    # CAPSTONE_UNMAPPED_BATCH10_V1: use previously saved metric counters;
    # add only enumerate; other metric preferences exist in batches 3/5.
    saved_metrics_b10 = _get_style_metrics(diff)
    target_metrics_b10 = _get_target_metrics(diff)
    for tag_b10, metric_b10, action_b10 in (
        ("enumerate 사용", "enumerate_call_count", "create_safe_enumerate"),
    ):
        if (_metric_count(saved_metrics_b10, metric_b10) > 0
                and _metric_count(target_metrics_b10, metric_b10) == 0):
            actions.append({
                "tag": tag_b10,
                "action": action_b10,
                "reason": "기존 저장 메트릭에 근거해 안전한 구문 패턴을 탐색합니다.",
            })

    # CAPSTONE_UNMAPPED_BATCH11_PLAN_V1: no change to the 19 saved syntax tags.
    # The same stored metric fields already used by previous style records
    # indicate preferences; require evidence in the candidate target as well.
    saved_b11 = _get_style_metrics(diff)
    target_b11 = _get_target_metrics(diff)
    for tag_b11, desired_b11, evidence_b11, action_b11 in (
        ("len 사용", "len_call_count", "sum_call_count", "create_safe_literal_len"),
        ("zip 사용", "zip_call_count", "loop_count", "create_safe_literal_zip"),
        ("슬라이싱 사용", "slicing_count", "list_method_call_count", "create_safe_list_slice"),
    ):
        if (_metric_count(saved_b11, desired_b11) > 0
                and _metric_count(target_b11, desired_b11) == 0
                and _metric_count(target_b11, evidence_b11) > 0):
            actions.append({
                "tag": tag_b11,
                "action": action_b11,
                "reason": "저장된 기존 메트릭으로 확인한 스타일 선호를 제한된 안전 패턴에 적용합니다.",
            })

    # CAPSTONE_UNMAPPED_BATCH12_PLAN_V1: infer preference only from preexisting
    # persisted metrics. No saved style/schema/frontend modifications.
    saved_b12 = _get_style_metrics(diff)
    target_b12 = _get_target_metrics(diff)
    safe_prefs_b12 = (
        ("continue문", "create_safe_guard_continue", "continue_count",
         ("loop_count", "if_count")),
        ("식별 비교", "create_safe_literal_identity", "identity_compare_count",
         ("compare_count", "none_count")),
        ("산술 연산", "create_safe_arithmetic_expression", "bin_op_count",
         ("call_count", "attribute_count", "import_count")),
    )
    for tag_b12, action_b12, preferred_b12, evidence_b12 in safe_prefs_b12:
        if (_metric_count(saved_b12, preferred_b12) > 0
                and _metric_count(target_b12, preferred_b12) == 0
                and all(_metric_count(target_b12, key) > 0 for key in evidence_b12)
                and not any(item.get("action") == action_b12 for item in actions)):
            actions.append({
                "tag": tag_b12,
                "action": action_b12,
                "reason": "기존 저장 메트릭의 스타일 선호가 확인된 안전한 국소 패턴만 변환합니다.",
            })

    # CAPSTONE_UNMAPPED_BATCH13_PLAN_V1: use existing persisted metrics only.
    # No changes to the 19 saved syntax preferences, APIs or frontend.
    saved_b13 = _get_style_metrics(diff)
    target_b13 = _get_target_metrics(diff)
    for tag_b13, metric_b13, action_b13 in (
        ("문자열 리터럴", "string_literal_count", "create_safe_string_literal"),
        ("숫자 리터럴", "number_literal_count", "create_safe_number_literal"),
        ("불리언 리터럴", "boolean_literal_count", "create_safe_boolean_literal"),
    ):
        if (_metric_count(saved_b13, metric_b13) > 0
                and _metric_count(target_b13, metric_b13) == 0
                and _metric_count(target_b13, "call_count") > 0
                and not any(item.get("action") == action_b13 for item in actions)):
            actions.append({
                "tag": tag_b13,
                "action": action_b13,
                "reason": "저장된 기존 리터럴 메트릭을 반영하되 기본 내장 함수의 상수 호출만 변환합니다.",
            })

    # CAPSTONE_BATCH19_METRIC_GATE_V1: require saved and target evidence.
    # Unobserved or ambiguous styles never create calls or comparisons.
    saved_b19 = _get_style_metrics(diff)
    target_b19 = _get_target_metrics(diff)
    for tag_b19, desired_b19, evidence_b19, action_b19 in (
        ("비교 연산", "compare_count", ("call_count", "import_count"),
         "create_safe_operator_comparison"),
        ("함수 호출", "call_count", ("bin_op_count", "import_count"),
         "create_safe_operator_call"),
    ):
        if (_metric_count(saved_b19, desired_b19) > 0
                and _metric_count(target_b19, desired_b19) == 0
                and all(_metric_count(target_b19, key) > 0 for key in evidence_b19)
                and not any(item.get("action") == action_b19 for item in actions)):
            actions.append({
                "tag": tag_b19,
                "action": action_b19,
                "reason": "저장 스타일의 기존 메트릭과 대상 operator 구문을 확인한 안전 패턴만 변환합니다.",
            })

    # CAPSTONE_BATCH20_METRIC_PLAN_V1: only observed style preferences.
    saved_b20 = _get_style_metrics(diff)
    target_b20 = _get_target_metrics(diff)
    for tag_b20, saved_metric, target_evidence, action_b20 in (
        ("None 사용", "none_count", ("dict_literal_count", "attribute_count", "call_count"),
         "create_safe_empty_dict_none"),
        ("print 사용", "print_call_count", ("import_count", "attribute_count", "call_count"),
         "create_safe_builtin_print"),
    ):
        if (_metric_count(saved_b20, saved_metric) > 0
                and _metric_count(target_b20, saved_metric) == 0
                and all(_metric_count(target_b20, metric) > 0 for metric in target_evidence)
                and not any(item.get("action") == action_b20 for item in actions)):
            actions.append({
                "tag": tag_b20,
                "action": action_b20,
                "reason": "저장 스타일의 기존 메트릭이 확인된 경우 안전한 국소 코드 패턴만 변경합니다.",
            })

    # CAPSTONE_BATCH21_METRIC_GATE_V1: only recorded preferences select actions.
    # Assert changes require an explicit __debug__ guard. Input only rewrites a
    # prior-imported builtins.input call without changing the prompt or stdin.
    saved_b21 = _get_style_metrics(diff)
    target_b21 = _get_target_metrics(diff)
    for tag_b21, saved_metric, evidence, action_b21 in (
        ("input 사용", "input_call_count", ("import_count", "attribute_count", "call_count"),
         "create_safe_builtin_input"),
        ("assert문", "assert_count", ("if_count", "raise_count"),
         "create_safe_debug_assert"),
    ):
        if (_metric_count(saved_b21, saved_metric) > 0
                and _metric_count(target_b21, saved_metric) == 0
                and all(_metric_count(target_b21, metric) > 0 for metric in evidence)
                and not any(item.get("action") == action_b21 for item in actions)):
            actions.append({
                "tag": tag_b21,
                "action": action_b21,
                "reason": "저장된 메트릭과 국소 코드 패턴에 근거한 안전한 변환만 실행합니다.",
            })

    # CAPSTONE_BATCH22_METRIC_GATE_V1: derive preference from stored metrics.
    # Unpacking constants is local and side-effect free. Debug assert expansion
    # keeps the explicit optimization guard; neither action is triggered by a
    # missing-tag label alone.
    saved_b22 = _get_style_metrics(diff)
    target_b22 = _get_target_metrics(diff)
    if (_metric_count(saved_b22, "assign_count") >
            _metric_count(target_b22, "assign_count") > 0
            and _metric_count(target_b22, "tuple_literal_count") > 0):
        actions.append({
            "tag": "변수 할당",
            "action": "create_safe_literal_unpack_assignments",
            "reason": "저장 스타일의 개별 대입문 선호와 상수 튜플 언패킹이 모두 확인된 경우에만 분리합니다.",
        })
    if (_metric_count(saved_b22, "raise_count") > 0
            and _metric_count(target_b22, "raise_count") == 0
            and _metric_count(target_b22, "assert_count") > 0
            and _metric_count(target_b22, "if_count") > 0):
        actions.append({
            "tag": "raise문",
            "action": "create_safe_debug_raise",
            "reason": "__debug__로 보호된 단순 assert만 명시적 예외 발생으로 변환합니다.",
        })

    # CAPSTONE_BATCH23_METRIC_GATE_V1: explicit saved preferences only.
    # Avoid introducing break guards when the saved style prefers for loops.
    saved_b23 = _get_style_metrics(diff)
    target_b23 = _get_target_metrics(diff)
    if (_metric_count(saved_b23, "break_count") > 0
            and _metric_count(target_b23, "break_count") == 0
            and _metric_count(target_b23, "loop_count") > 0
            and not prefer_for
            and not any(item.get("action") in {"create_while_iteration", "create_counted_while_to_for"}
                        for item in actions)):
        actions.append({
            "tag": "break문",
            "action": "create_safe_counted_break",
            "reason": "정수 카운터가 명확한 while 반복문에만 종료 조건의 break 가드를 명시합니다.",
        })
    if (_metric_count(saved_b23, "global_count") > 0
            and _metric_count(target_b23, "global_count") == 0
            and _metric_count(target_b23, "function_count") > 0
            and _metric_count(target_b23, "assign_count") > 0):
        actions.append({
            "tag": "전역 변수 사용",
            "action": "create_safe_readonly_global",
            "reason": "모듈에 정의된 상수를 읽기만 하는 단순 함수에 명시적 global 선언을 추가합니다.",
        })

    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:
        tag_name = _get_tag_name(tag_item)
        if not tag_name:
            continue
        action = get_create_action_for_tag(tag_name)
        if action is None:
            compare_only.append(tag_name)
            continue
        if tag_name in {"비교 연산", "함수 호출"}:
            continue  # Batch 19: metric gate above is required.
        # CAPSTONE_BATCH23_METRIC_ONLY_V1: missing tags alone never trigger generation.
        if tag_name in {"break문", "전역 변수 사용"}:
            continue
        # CAPSTONE_BATCH22_METRIC_ONLY_V1: no blind transforms from a missing tag.
        if tag_name in {"변수 할당", "raise문"}:
            continue
        # CAPSTONE_BATCH21_METRIC_ONLY_V1: unobserved tag name is not enough.
        if tag_name in {"input 사용", "assert문"}:
            continue
        # CAPSTONE_BATCH20_METRIC_ONLY_V1: missing-tag evidence alone is insufficient.
        if tag_name in {"None 사용", "print 사용"}:
            continue

        # CAPSTONE_UNMAPPED_BATCH13_METRIC_ONLY_V1: never select these actions
        # from a missing-tag record alone; only the gated metrics above may.
        if action in {
            "create_safe_string_literal",
            "create_safe_number_literal",
            "create_safe_boolean_literal",
        }:
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

        # CAPSTONE_UNMAPPED_BATCH2_V1: do not undo stronger saved preferences.
        # A nested style should not be flattened merely to create a broad
        # validation concept, and a state-mutation style should not be summed.
        saved_concepts = _get_tag_names(diff, "style_concept_names")
        if tag_name == "검증 로직 중심 구조" and saved_concepts & {
            "조건문 중첩 구조", "깊은 중첩 구조"
        }:
            continue
        if tag_name == "내장 함수 활용 구조" and "상태 변경 중심 구조" in saved_concepts:
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
