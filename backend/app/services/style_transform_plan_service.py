
from app.services.style_tag_transform_map_service import (
    get_create_action_for_tag,
)


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

    if not isinstance(tag_name, str):
        return ""

    return tag_name


def _deduplicate_actions(actions: list[dict]) -> list[dict]:
    """
    동일한 태그와 변환 액션의 중복 등록을 방지합니다.
    """

    unique_actions = []
    seen = set()

    for item in actions:
        key = (
            item.get("tag"),
            item.get("action"),
        )

        if key in seen:
            continue

        seen.add(key)
        unique_actions.append(item)

    return unique_actions


def _get_tag_names(diff: dict, key: str) -> set[str]:
    """
    스타일 비교 결과에 포함된 태그 이름을 집합으로 반환합니다.

    해당 정보가 없는 이전 버전의 비교 결과도 허용합니다.
    """

    values = diff.get(key)

    if not isinstance(values, (set, list, tuple)):
        return set()

    return {
        value
        for value in values
        if isinstance(value, str)
    }


def _get_style_metrics(diff: dict) -> dict:
    """
    저장된 스타일의 메트릭을 가져옵니다.

    style_diff_service에서 전달하지 않았다면 빈 딕셔너리를
    반환하여 기존 변환 계획의 동작을 유지합니다.
    """

    metrics = diff.get("style_metrics", {})

    if not isinstance(metrics, dict):
        return {}

    return metrics


def _get_target_metrics(diff: dict) -> dict:
    """
    대상 코드 분석 결과의 메트릭을 가져옵니다.
    """

    analysis = diff.get("target_analysis", {})

    if not isinstance(analysis, dict):
        return {}

    metrics = analysis.get("metrics", {})

    if not isinstance(metrics, dict):
        return {}

    return metrics


def _metric_count(metrics: dict, key: str) -> int:
    """
    메트릭의 정수 값을 안전하게 가져옵니다.
    """

    value = metrics.get(key, 0)

    if type(value) is not int:
        return 0

    return max(value, 0)


def _prefer_filtered_comprehension(diff: dict) -> bool:
    """
    저장된 스타일이 리스트 컴프리헨션 필터링을 사용하고,
    대상 코드는 반복문 기반 필터링을 사용하는지 확인합니다.

    실제 변환 가능 여부는 전용 변환기에서 검사합니다.
    """

    if (
        get_create_action_for_tag(FILTER_CONCEPT_TAG)
        != "create_filter_style"
    ):
        return False

    style_syntax = _get_tag_names(
        diff,
        "style_syntax_names",
    )

    style_concept = _get_tag_names(
        diff,
        "style_concept_names",
    )

    target_syntax = _get_tag_names(
        diff,
        "target_syntax_names",
    )

    target_concept = _get_tag_names(
        diff,
        "target_concept_names",
    )

    target_metrics = _get_target_metrics(diff)

    return (
        FILTER_CONCEPT_TAG in style_concept
        and LIST_COMPREHENSION_TAG in style_syntax
        and FILTER_CONCEPT_TAG in target_concept
        and LIST_COMPREHENSION_TAG not in target_syntax
        and "for문" in target_syntax
        and _metric_count(
            target_metrics,
            "append_call_count",
        ) >= 1
        and _metric_count(
            target_metrics,
            "filter_pattern_count",
        ) >= 1
    )


def _prefer_sorted_style(diff: dict) -> bool:
    """
    저장된 스타일과 대상 코드의 정렬 방식 차이를 확인합니다.

    저장된 스타일:
        sorted() 중심

    대상 코드:
        list.sort() 중심

    두 코드 모두 '정렬 중심 구조' 태그를 갖더라도
    구체적인 정렬 방식이 다르면 변환을 계획합니다.

    필요한 메트릭:
        style_metrics["sorted_call_count"]
        style_metrics["sort_method_call_count"]
        target_metrics["sorted_call_count"]
        target_metrics["sort_method_call_count"]

    메트릭이 전달되지 않으면 변환을 강제하지 않습니다.
    """

    if (
        get_create_action_for_tag(SORT_CONCEPT_TAG)
        != "create_sort_style"
    ):
        return False

    style_concept = _get_tag_names(
        diff,
        "style_concept_names",
    )

    target_concept = _get_tag_names(
        diff,
        "target_concept_names",
    )

    if SORT_CONCEPT_TAG not in style_concept:
        return False

    if SORT_CONCEPT_TAG not in target_concept:
        return False

    style_metrics = _get_style_metrics(diff)
    target_metrics = _get_target_metrics(diff)

    style_sorted_count = _metric_count(
        style_metrics,
        "sorted_call_count",
    )

    style_sort_method_count = _metric_count(
        style_metrics,
        "sort_method_call_count",
    )

    target_sorted_count = _metric_count(
        target_metrics,
        "sorted_call_count",
    )

    target_sort_method_count = _metric_count(
        target_metrics,
        "sort_method_call_count",
    )

    # 저장된 스타일이 sorted()만 사용하는 경우에 한합니다.
    if style_sorted_count < 1:
        return False

    if style_sort_method_count > 0:
        return False

    # 대상 코드가 list.sort()를 사용해야 합니다.
    if target_sort_method_count < 1:
        return False

    # 대상 코드가 이미 sorted()도 사용한다면
    # 혼합 정렬 방식으로 보고 자동 변경을 강제하지 않습니다.
    if target_sorted_count > 0:
        return False

    return True


def _build_filter_comprehension_action() -> dict:
    """
    반복문 기반 필터링을 리스트 컴프리헨션으로
    변경하기 위한 액션을 생성합니다.
    """

    return {
        "tag": FILTER_CONCEPT_TAG,
        "action": "create_filter_style",
        "reason": (
            "저장된 코딩 스타일은 데이터 필터링에 "
            "리스트 컴프리헨션을 사용하지만, "
            "대상 코드는 반복문과 append 호출을 사용합니다. "
            "필터링 동작을 유지하는 범위에서 "
            "리스트 컴프리헨션 변환을 시도합니다."
        ),
    }


def _build_sorted_style_action() -> dict:
    """
    list.sort() 방식에서 sorted() 방식으로
    변경하기 위한 액션을 생성합니다.
    """

    return {
        "tag": SORT_CONCEPT_TAG,
        "action": "create_sort_style",
        "reason": (
            "저장된 코딩 스타일은 sorted() 함수를 사용하지만, "
            "대상 코드는 리스트의 sort() 메서드를 사용합니다. "
            "원본 리스트 참조와 정렬 결과에 영향을 주지 않는 "
            "안전한 패턴에서 sorted() 방식으로 변환을 시도합니다."
        ),
    }


def build_transform_plan(diff: dict) -> dict:
    """
    저장된 코딩 스타일을 목표로 변환 계획을 생성합니다.

    핵심 원칙:
    1. 저장된 코딩 스타일을 기준으로 변환합니다.
    2. 대상 코드에 없는 목표 태그를 확인합니다.
    3. 실제 변환기가 연결된 태그만 계획에 추가합니다.
    4. 자동 변환 미지원 태그는 비교 대상으로 유지합니다.
    5. 코드의 좋고 나쁨을 평가하지 않습니다.
    6. 데이터 필터링은 문법 방식의 차이도 비교합니다.
    7. 정렬은 메트릭이 충분한 경우 정렬 방식도 비교합니다.
    8. 동일한 목적의 변환 액션을 중복 실행하지 않습니다.
    """

    missing_syntax_tags = diff.get(
        "missing_syntax_tags",
        [],
    )

    missing_concept_tags = diff.get(
        "missing_concept_tags",
        [],
    )

    actions = []
    compare_only = []

    # 1. 필터링 방식 차이를 확인합니다.
    prefer_filter = _prefer_filtered_comprehension(diff)

    if prefer_filter:
        actions.append(
            _build_filter_comprehension_action()
        )

    # 2. 정렬 방식 차이를 확인합니다.
    prefer_sort = _prefer_sorted_style(diff)

    if prefer_sort:
        actions.append(
            _build_sorted_style_action()
        )

    # 3. 기존 누락 태그 기반 변환 계획을 유지합니다.
    for tag_item in [
        *missing_syntax_tags,
        *missing_concept_tags,
    ]:
        tag_name = _get_tag_name(tag_item)

        if not tag_name:
            continue

        action = get_create_action_for_tag(tag_name)

        if action is not None:
            # 이미 필터링 전용 변환을 계획했다면
            # 일반 리스트 컴프리헨션 변환을 중복하지 않습니다.
            if (
                prefer_filter
                and action == "create_comprehension_collection"
                and tag_name in FILTER_RELATED_COMPREHENSION_TAGS
            ):
                continue

            # 이미 정렬 방식 변환을 계획했다면
            # 같은 정렬 액션을 중복하지 않습니다.
            if (
                prefer_sort
                and action == "create_sort_style"
            ):
                continue

            actions.append(
                {
                    "tag": tag_name,
                    "action": action,
                    "reason": (
                        f"저장된 코딩 스타일에는 '{tag_name}' "
                        "태그가 있지만 대상 코드에는 없으므로, "
                        "해당 스타일을 반영하는 변환을 시도합니다."
                    ),
                }
            )

            continue

        # 연결되지 않은 태그도 스타일 비교 기준으로 유지합니다.
        compare_only.append(tag_name)

    return {
        "actions": _deduplicate_actions(actions),
        "compare_only": sorted(set(compare_only)),
    }
