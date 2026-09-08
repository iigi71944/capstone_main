import ast

from app.services.parser_service import parse_code
from app.services.syntax_tag_service import extract_syntax_tags
from app.services.metric_service import calculate_metrics
from app.services.concept_tag_service import extract_concept_tags

from app.services.improvement.beginner_friendly_service import (
    transform_to_beginner_friendly,
)
from app.services.improvement.concise_service import transform_to_concise
from app.services.improvement.structured_service import transform_to_structured
from app.services.improvement.data_processing_service import (
    transform_data_processing_style,
)
from app.services.improvement.resource_style_service import (
    transform_resource_style,
)
from app.services.improvement.string_style_service import (
    transform_string_style,
)
from app.services.improvement.search_style_service import (
    transform_search_style,
)


VALID_MODES = {"beginner", "concise", "structured"}


def normalize_code(code: str) -> str:
    try:
        tree = ast.parse(code)
        return ast.unparse(tree).strip()
    except Exception:
        return code.strip()


def has_valid_python_syntax(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def has_changed(original_code: str, improved_code: str) -> bool:
    return normalize_code(original_code) != normalize_code(improved_code)


def analyze_code_profile(code: str) -> dict:
    tree = parse_code(code)
    syntax_tags = extract_syntax_tags(tree)
    metrics = calculate_metrics(tree)
    concept_tags = extract_concept_tags(metrics)

    return {
        "syntax_tags": syntax_tags,
        "concept_tags": concept_tags,
        "metrics": metrics,
    }


def get_beginner_direction_tags(profile: dict) -> list[str]:
    result = []

    for tag in profile["syntax_tags"]:
        tag_name = tag.get("tag", "")
        grammar_level = tag.get("grammar_level", "")
        difficulty = tag.get("difficulty", "")
        style_role = tag.get("style_role", "")
        allowed = tag.get("allowed_in_beginner", False)

        if (
            not allowed
            or grammar_level == "상위 문법"
            or difficulty in {"중간 문법", "어려운 문법"}
            or "간결" in style_role
        ):
            result.append(tag_name)

    for tag in profile["concept_tags"]:
        tag_name = tag.get("tag", "")
        concept_level = tag.get("concept_level", "")
        difficulty = tag.get("difficulty", "")
        allowed = tag.get("allowed_in_beginner", False)

        if (
            not allowed
            or concept_level in {"중간 구조", "복잡 구조"}
            or difficulty in {"중간 구조", "어려운 구조"}
        ):
            result.append(tag_name)

    return sorted(set(result))


def get_concise_direction_tags(profile: dict) -> list[str]:
    result = []

    for tag in profile["syntax_tags"]:
        tag_name = tag.get("tag", "")
        category = tag.get("category", "")
        style_role = tag.get("style_role", "")
        allowed = tag.get("allowed_in_concise", False)

        if (
            allowed
            and (
                "간결" in style_role
                or "집계" in style_role
                or "정렬" in style_role
                or "문자열" in style_role
                or category in {"리스트", "딕셔너리", "세트", "제너레이터", "내장 함수", "문자열"}
            )
        ):
            result.append(tag_name)

    for tag in profile["concept_tags"]:
        tag_name = tag.get("tag", "")
        category = tag.get("category", "")
        style_role = tag.get("style_role", "")
        allowed = tag.get("allowed_in_concise", False)

        if (
            allowed
            and (
                "간결" in style_role
                or "데이터" in style_role
                or "집계" in style_role
                or "정렬" in style_role
                or "필터링" in style_role
                or "변환" in style_role
                or "문자열" in style_role
                or "탐색" in style_role
                or category in {"데이터 처리", "정렬", "리스트", "컴프리헨션", "문자열", "탐색"}
            )
        ):
            result.append(tag_name)

    return sorted(set(result))


def get_structured_direction_tags(profile: dict) -> list[str]:
    result = []

    for tag in profile["syntax_tags"]:
        tag_name = tag.get("tag", "")
        category = tag.get("category", "")
        style_role = tag.get("style_role", "")
        allowed = tag.get("allowed_in_structured", False)

        if (
            allowed
            and (
                "구조" in style_role
                or "방어" in style_role
                or "상태" in style_role
                or "파일" in style_role
                or category in {"예외 처리", "자원 관리", "객체지향", "조건문", "입출력"}
            )
        ):
            result.append(tag_name)

    for tag in profile["concept_tags"]:
        tag_name = tag.get("tag", "")
        concept_level = tag.get("concept_level", "")
        category = tag.get("category", "")
        style_role = tag.get("style_role", "")
        allowed = tag.get("allowed_in_structured", False)

        if (
            allowed
            and (
                "구조" in style_role
                or "복잡도" in style_role
                or "리팩토링" in style_role
                or "안정성" in style_role
                or "파일" in style_role
                or "입출력" in style_role
                or concept_level == "복잡 구조"
                or category in {"구조화", "복잡도", "자원 관리", "파일 입출력", "검증", "입출력"}
            )
        ):
            result.append(tag_name)

    return sorted(set(result))


def get_mode_direction_tags(profile: dict, mode: str) -> list[str]:
    if mode == "beginner":
        return get_beginner_direction_tags(profile)

    if mode == "concise":
        return get_concise_direction_tags(profile)

    if mode == "structured":
        return get_structured_direction_tags(profile)

    return []


def get_mode_goal_message(mode: str) -> str:
    if mode == "beginner":
        return (
            "학습 친화형은 실행 결과를 유지하면서 상위 문법이나 어려운 문법을 "
            "초보자가 이해하기 쉬운 명시적인 구조로 풀어 쓰는 것을 목표로 합니다."
        )

    if mode == "concise":
        return (
            "간결성 중심형은 실행 결과를 유지하면서 반복 누적, 필터링, 변환, 집계, 문자열 처리, 탐색 구조를 "
            "더 짧고 간단한 표현으로 통합하는 것을 목표로 합니다."
        )

    if mode == "structured":
        return (
            "구조 중심형은 실행 결과를 유지하면서 불필요한 else, 중복 return, 중첩 if, "
            "자원 관리 흐름 등을 정리하는 것을 목표로 합니다."
        )

    return "지원하지 않는 개선 모드입니다."


def apply_mode_transform(code: str, mode: str) -> str:
    if mode == "beginner":
        return transform_to_beginner_friendly(code)

    if mode == "concise":
        transformed = transform_to_concise(code)
        transformed = transform_data_processing_style(transformed)
        transformed = transform_string_style(transformed)
        transformed = transform_search_style(transformed)
        transformed = transform_to_structured(transformed)
        return transformed

    if mode == "structured":
        transformed = transform_to_structured(code)
        transformed = transform_resource_style(transformed)
        return transformed

    return code


def validate_improved_code(
    original_code: str,
    improved_code: str,
    mode: str,
    direction_tags: list[str],
) -> tuple[bool, str]:
    if mode not in VALID_MODES:
        return False, "지원하지 않는 개선 모드이므로 결과를 출력하지 않습니다."

    if not improved_code.strip():
        return False, "개선 결과 코드가 비어 있어 출력하지 않습니다."

    if not has_valid_python_syntax(improved_code):
        return False, "개선 결과 코드에 Python 문법 오류가 있어 출력하지 않습니다."

    if not has_changed(original_code, improved_code):
        if direction_tags:
            return (
                False,
                "현재 코드에서 개선 방향과 관련된 태그는 감지되었지만, 실행 결과를 유지하면서 안전하게 바꿀 수 있는 패턴이 발견되지 않아 결과를 출력하지 않습니다.",
            )

        return (
            False,
            "현재 코드에서 해당 모드의 개선 방향과 직접 연결되는 태그 또는 안전한 변환 패턴이 발견되지 않아 결과를 출력하지 않습니다.",
        )

    if not direction_tags:
        return (
            False,
            "코드는 변환되었지만, 현재 모드의 태그 규칙 기준과 연결되는 개선 방향이 충분히 확인되지 않아 결과를 출력하지 않습니다.",
        )

    return True, "검증을 통과했습니다."


def build_summary(mode: str, direction_tags: list[str]) -> str:
    mode_goal = get_mode_goal_message(mode)

    if direction_tags:
        tag_text = ", ".join(direction_tags[:10])
        if len(direction_tags) > 10:
            tag_text += " 외 추가 태그"

        return (
            f"{mode_goal} "
            f"이번 개선에서는 태그 규칙 기준으로 [{tag_text}] 항목을 주요 판단 근거로 사용했습니다. "
            "또한 개선 전 코드와 개선 후 코드의 실행 결과가 같아야 한다는 공통 조건을 기준으로, "
            "안전한 변환 패턴에 해당하는 경우에만 개선 결과를 출력했습니다."
        )

    return (
        f"{mode_goal} "
        "다만 현재 코드에서는 해당 모드의 태그 규칙과 직접 연결되는 개선 대상이 충분히 감지되지 않았습니다. "
        "따라서 실행 결과 보존이 가능한 안전한 변환이 확인되는 경우에만 결과를 출력합니다."
    )


def improve_code(code: str, mode: str):
    try:
        original_profile = analyze_code_profile(code)
    except SyntaxError as e:
        return "", f"문법 오류가 있어 개선을 수행할 수 없습니다: {e.msg} (line {e.lineno})"
    except Exception as e:
        return "", f"코드 분석 중 오류가 발생하여 개선을 수행할 수 없습니다: {str(e)}"

    direction_tags = get_mode_direction_tags(original_profile, mode)
    improved = apply_mode_transform(code, mode)

    is_valid, message = validate_improved_code(
        original_code=code,
        improved_code=improved,
        mode=mode,
        direction_tags=direction_tags,
    )

    if not is_valid:
        return "", message

    summary = build_summary(mode, direction_tags)
    return improved, summary