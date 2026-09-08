from app.services.parser_service import parse_code
from app.services.syntax_tag_service import extract_syntax_tags
from app.services.metric_service import calculate_metrics
from app.services.concept_tag_service import extract_concept_tags


def _get_tag_map(tags: list[dict]) -> dict[str, dict]:
    return {item.get("tag", ""): item for item in tags if item.get("tag")}


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

    style_syntax_map = _get_tag_map(style.get("syntax_tags", []))
    style_concept_map = _get_tag_map(style.get("concept_tags", []))

    target_syntax_map = _get_tag_map(target_analysis.get("syntax_tags", []))
    target_concept_map = _get_tag_map(target_analysis.get("concept_tags", []))

    style_syntax_names = set(style_syntax_map.keys())
    style_concept_names = set(style_concept_map.keys())

    target_syntax_names = set(target_syntax_map.keys())
    target_concept_names = set(target_concept_map.keys())

    missing_syntax_names = sorted(style_syntax_names - target_syntax_names)
    missing_concept_names = sorted(style_concept_names - target_concept_names)

    extra_syntax_names = sorted(target_syntax_names - style_syntax_names)
    extra_concept_names = sorted(target_concept_names - style_concept_names)

    return {
        "target_analysis": target_analysis,
        "missing_syntax_tags": [
            style_syntax_map[name] for name in missing_syntax_names
        ],
        "missing_concept_tags": [
            style_concept_map[name] for name in missing_concept_names
        ],
        "extra_syntax_tags": [
            target_syntax_map[name] for name in extra_syntax_names
        ],
        "extra_concept_tags": [
            target_concept_map[name] for name in extra_concept_names
        ],
        "style_syntax_names": style_syntax_names,
        "style_concept_names": style_concept_names,
        "target_syntax_names": target_syntax_names,
        "target_concept_names": target_concept_names,
    }


def compare_after_transform(style: dict, transformed_code: str) -> dict:
    return compare_style_with_target_code(style=style, code=transformed_code)