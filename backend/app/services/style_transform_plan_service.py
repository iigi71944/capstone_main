
from app.services.style_tag_transform_map_service import (
    get_create_action_for_tag,
)


def _get_tag_name(tag_item: dict) -> str:
    return tag_item.get("tag", "")


def _deduplicate_actions(actions: list[dict]) -> list[dict]:
    """
    동일한 태그와 변환 액션이 중복 등록되지 않도록 처리합니다.
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


def build_transform_plan(diff: dict) -> dict:
    """
    저장된 코딩 스타일 태그를 목표로 변환 계획을 생성합니다.

    핵심 원칙:
    1. 저장된 코딩 스타일을 기준으로 변환합니다.
    2. 대상 코드에 없는 목표 태그를 확인합니다.
    3. 실제 변환기가 연결된 태그만 변환 계획에 추가합니다.
    4. 자동 변환을 지원하지 않는 태그는 비교 대상으로 유지합니다.
    5. 코드의 좋고 나쁨이나 개선 필요성을 판단하지 않습니다.
    """

    missing_syntax_tags = diff.get(
        "missing_syntax_tags", []
    )

    missing_concept_tags = diff.get(
        "missing_concept_tags", []
    )

    actions = []
    compare_only = []

    for tag_item in [
        *missing_syntax_tags,
        *missing_concept_tags,
    ]:
        tag_name = _get_tag_name(tag_item)

        if not tag_name:
            continue

        action = get_create_action_for_tag(tag_name)

        if action is not None:
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

        # 변환기가 없는 태그도 코딩 스타일의 특징입니다.
        # 임의로 코드를 수정하지 않고 비교 기준으로 유지합니다.
        compare_only.append(tag_name)

    return {
        "actions": _deduplicate_actions(actions),
        "compare_only": sorted(set(compare_only)),
    }
