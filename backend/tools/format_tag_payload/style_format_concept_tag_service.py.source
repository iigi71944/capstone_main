"""Build saved-style concept tags from the existing, read-only formatting profile.

These are *formatting metadata tags*, not code-structure transformation actions.
Existing structural tag rules and their 102-tag audit remain unchanged.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.tag_rule_service import enrich_concept_tag


def _object(value: Any) -> dict:
    return deepcopy(value) if isinstance(value, dict) else {}


def build_formatting_concept_tags(profile: dict[str, Any]) -> list[dict]:
    """Return two JSON-compatible concept tags with their measured evidence.

    The precise extraction remains in extract_formatting_style(). A short or
    empty source receives explicit no-evidence messages, never invented values.
    """
    if not isinstance(profile, dict):
        raise TypeError("formatting profile must be a dictionary")

    indentation = _object(profile.get("indentation"))
    line_layout = _object(profile.get("line_layout"))
    line_endings = _object(profile.get("line_endings"))
    kind = indentation.get("kind")
    unit = indentation.get("unit_columns")
    occurrences = indentation.get("indentation_occurrences")
    observed_indent = bool(isinstance(occurrences, int) and occurrences > 0)

    if observed_indent:
        kind_text = {"spaces": "공백", "tabs": "탭", "mixed": "탭·공백 혼합"}.get(kind, "미분류")
        unit_text = f", 들여쓰기 간격 {unit}열" if isinstance(unit, int) and unit > 0 else ""
        indent_reason = f"원본 코드에서 {kind_text} 들여쓰기를 관측했습니다{unit_text}."
    else:
        indent_reason = "블록 들여쓰기가 관측되지 않아 방식과 간격을 추정하지 않았습니다."

    preferred_ending = line_endings.get("preferred")
    line_count = line_layout.get("logical_statements")
    observed_lines = bool(isinstance(line_count, int) and line_count > 0)
    if observed_lines:
        ending_text = {"lf": "LF", "crlf": "CRLF", "cr": "CR"}.get(preferred_ending, "미확인")
        line_reason = f"문장별 줄 배치와 빈 줄 분포를 저장했습니다. 줄 끝 형식: {ending_text}."
    else:
        line_reason = "관측 가능한 코드 문장이 없어 줄 바꿈 형태를 추정하지 않았습니다."

    return [
        enrich_concept_tag({
            "tag": "들여쓰기",
            "score": 1.0 if observed_indent else 0.0,
            "reason": indent_reason,
            "details": indentation,
        }),
        enrich_concept_tag({
            "tag": "줄 바꿈",
            "score": 1.0 if observed_lines else 0.0,
            "reason": line_reason,
            "details": {
                "line_layout": line_layout,
                "line_endings": line_endings,
            },
        }),
    ]
