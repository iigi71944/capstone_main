
from app.services.parser_service import parse_code
from app.services.syntax_tag_service import extract_syntax_tags
from app.services.metric_service import calculate_metrics
from app.services.concept_tag_service import extract_concept_tags
from app.services.tag_rule_service import CONCEPT_TAG_RULES


def _get_tag_map(
    tags: list[dict],
    allowed_tags: set[str] | None = None,
) -> dict[str, dict]:
    """태그 목록을 이름별로 정리하고 유효한 태그만 남깁니다."""
    tag_map = {}

    for item in tags or []:
        if not isinstance(item, dict):
            continue

        tag_name = item.get("tag")
        if not isinstance(tag_name, str) or not tag_name:
            continue

        if allowed_tags is not None and tag_name not in allowed_tags:
            continue

        tag_map[tag_name] = item

    return tag_map


def analyze_code_style(code: str) -> dict:
    tree = parse_code(code)
    syntax_tags = extract_syntax_tags(tree)
    metrics = calculate_metrics(tree)
    concept_tags = extract_concept_tags(metrics)

    return {
        "syntax_tags": syntax_tags,
        "concept_tags": concept_tags,
        "metrics": metrics,
    }


def compare_style_with_target_code(style: dict, code: str) -> dict:
    target_analysis = analyze_code_style(code)

    # 과거 저장된 스타일의 삭제/미등록 개념 태그는
    # 비교 및 변환 목표에서만 제외합니다.
    # 기존 저장 데이터는 수정하지 않습니다.
    valid_concept_tags = set(CONCEPT_TAG_RULES)

    style_syntax_map = _get_tag_map(style.get("syntax_tags", []))
    style_concept_map = _get_tag_map(
        style.get("concept_tags", []),
        valid_concept_tags,
    )

    target_syntax_map = _get_tag_map(
        target_analysis.get("syntax_tags", [])
    )
    target_concept_map = _get_tag_map(
        target_analysis.get("concept_tags", []),
        valid_concept_tags,
    )

    style_syntax_names = set(style_syntax_map.keys())
    style_concept_names = set(style_concept_map.keys())

    target_syntax_names = set(target_syntax_map.keys())
    target_concept_names = set(target_concept_map.keys())

    missing_syntax_names = sorted(
        style_syntax_names - target_syntax_names
    )
    missing_concept_names = sorted(
        style_concept_names - target_concept_names
    )

    extra_syntax_names = sorted(
        target_syntax_names - style_syntax_names
    )
    extra_concept_names = sorted(
        target_concept_names - style_concept_names
    )

    return {
        "target_analysis": target_analysis,
        "missing_syntax_tags": [
            style_syntax_map[name]
            for name in missing_syntax_names
        ],
        "missing_concept_tags": [
            style_concept_map[name]
            for name in missing_concept_names
        ],
        "extra_syntax_tags": [
            target_syntax_map[name]
            for name in extra_syntax_names
        ],
        "extra_concept_tags": [
            target_concept_map[name]
            for name in extra_concept_names
        ],
        "style_syntax_names": style_syntax_names,
        "style_concept_names": style_concept_names,
        "target_syntax_names": target_syntax_names,
        "target_concept_names": target_concept_names,
    }


def compare_after_transform(style: dict, transformed_code: str) -> dict:
    return compare_style_with_target_code(
        style=style,
        code=transformed_code,
    )
