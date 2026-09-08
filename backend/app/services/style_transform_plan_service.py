from app.services.style_tag_transform_map_service import (
    get_create_action_for_tag,
    is_compare_only_tag,
    is_refactor_guide_tag,
)


def _get_tag_name(tag_item: dict) -> str:
    return tag_item.get("tag", "")


def _deduplicate_actions(actions: list[dict]) -> list[dict]:
    unique_actions = []
    seen = set()

    for item in actions:
        key = (item.get("tag"), item.get("action"))

        if key in seen:
            continue

        seen.add(key)
        unique_actions.append(item)

    return unique_actions


def build_transform_plan(diff: dict) -> dict:
    """
    저장된 스타일 태그를 목표 상태로 삼아 변환 계획을 생성합니다.

    중요:
    - 대상 코드가 개선 가능한지 판단하지 않습니다.
    - 저장된 스타일에 있는데 대상 코드에 없는 태그만 목표 태그로 봅니다.
    - 목표 태그를 만들 수 있는 변환기만 실행 계획에 넣습니다.
    """

    missing_syntax_tags = diff.get("missing_syntax_tags", [])
    missing_concept_tags = diff.get("missing_concept_tags", [])

    actions = []
    refactor_guides = []
    compare_only = []

    for tag_item in [*missing_syntax_tags, *missing_concept_tags]:
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
                        f"저장된 코딩 스타일에는 '{tag_name}' 태그가 있지만 "
                        "대상 코드에는 부족하므로, 해당 스타일 태그를 생성하는 방향으로 변환을 시도합니다."
                    ),
                }
            )
            continue

        if is_refactor_guide_tag(tag_name):
            refactor_guides.append(tag_name)
            continue

        if is_compare_only_tag(tag_name):
            compare_only.append(tag_name)
            continue

        compare_only.append(tag_name)

    return {
        "actions": _deduplicate_actions(actions),
        "refactor_guides": sorted(set(refactor_guides)),
        "compare_only": sorted(set(compare_only)),
    }