from app.services.style_analysis_comment_filter_service import without_analysis_comments

from app.services.parser_service import parse_code
from app.services.syntax_tag_service import extract_syntax_tags
from app.services.metric_service import calculate_metrics
from app.services.style_metric_snapshot_service import normalize_style_metric_snapshot
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


def _get_style_metrics(style: dict) -> dict:
    """
    저장된 코딩 스타일의 메트릭을 반환합니다.

    저장된 스타일에는 분석 당시의 metrics가 포함됩니다.
    과거 저장 데이터에 해당 필드가 없다면 빈 딕셔너리를 사용합니다.

    원본 스타일 객체가 수정되지 않도록 복사본을 반환합니다.
    """

    metrics = style.get("metrics", {})

    if not isinstance(metrics, dict):
        return {}

    return metrics.copy()


def analyze_code_style(code: str) -> dict:
    tree = without_analysis_comments(parse_code(code))

    syntax_tags = extract_syntax_tags(tree)
    metrics = calculate_metrics(tree)
    concept_tags = extract_concept_tags(metrics)

    return {
        "syntax_tags": syntax_tags,
        "concept_tags": concept_tags,
        "metrics": metrics,
    }


def compare_style_with_target_code(style: dict, code: str) -> dict:
    """
    저장된 코딩 스타일과 대상 코드를 비교합니다.

    문법 태그와 개념 태그의 차이를 계산하며,
    정렬 방식 등 세부 문법 비교에 사용할 수 있도록
    저장된 스타일의 메트릭도 함께 전달합니다.

    메트릭만으로 코드의 좋고 나쁨을 판단하지 않습니다.
    """

    target_analysis = analyze_code_style(code)

    # 저장된 스타일에 포함된 메트릭을 가져옵니다.
    # 과거 스타일 데이터는 빈 딕셔너리로 처리합니다.
    # CAPSTONE_BATCH35_4_METRIC_VERSION_V1: track observed counters without inventing zeros.
    style_metrics, style_metrics_info = normalize_style_metric_snapshot(style)

    # 과거 저장된 스타일의 삭제/미등록 개념 태그는
    # 비교 및 변환 목표에서만 제외합니다.
    # 기존 저장 데이터는 수정하지 않습니다.
    valid_concept_tags = set(CONCEPT_TAG_RULES)

    style_syntax_map = _get_tag_map(
        style.get("syntax_tags", [])
    )

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
        # 대상 코드의 실제 분석 결과
        "target_analysis": target_analysis,

        # 저장된 스타일 분석 당시의 메트릭
        "style_metrics": style_metrics,
        "style_metrics_info": style_metrics_info,

        # 저장된 스타일에는 있지만 대상 코드에는 없는 태그
        "missing_syntax_tags": [
            style_syntax_map[name]
            for name in missing_syntax_names
        ],
        "missing_concept_tags": [
            style_concept_map[name]
            for name in missing_concept_names
        ],

        # 대상 코드에는 있지만 저장된 스타일에는 없는 태그
        "extra_syntax_tags": [
            target_syntax_map[name]
            for name in extra_syntax_names
        ],
        "extra_concept_tags": [
            target_concept_map[name]
            for name in extra_concept_names
        ],

        # 문법 방식 비교와 기존 변환 계획에 사용하는 태그 집합
        "style_syntax_names": style_syntax_names,
        "style_concept_names": style_concept_names,
        "target_syntax_names": target_syntax_names,
        "target_concept_names": target_concept_names,
    }


def compare_after_transform(
    style: dict,
    transformed_code: str,
) -> dict:
    """
    스타일 변환 이후 최종 코드를 다시 분석합니다.

    초기 비교와 동일한 기준을 적용하며,
    저장된 스타일의 메트릭은 변경하지 않습니다.
    """

    return compare_style_with_target_code(
        style=style,
        code=transformed_code,
    )
