"""34차: 대표 사례에서 실제 스타일 계획 -> 적용 -> 엄격한 실행 검증 감사.

목적: 33차의 '공개 변환기 직접 호출 5/6'과 생산 경로의 선택 액션을
구분한다. 원본 사용자 코드는 실행하지 않으며 저장소 내 신뢰된
테스트 예제만 기존 제한 실행기로 비교한다. 본 검증은 모든 Python
프로그램의 의미 동등성이나 실제 사용자 스타일 분포를 보장하지 않는다.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
for folder in (BACKEND, BACKEND / "tools", BACKEND / "tests"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import audit_transform_batch33 as previous
from app.services.style_tag_transform_map_service import CREATE_ACTION_BY_TAG
from app.services.style_transform_plan_service import build_transform_plan
from app.services.style_apply_service import (
    _apply_style_action,
    _get_transform_function,
    apply_coding_style,
)
from app.services.tag_rule_service import SYNTAX_TAG_RULES, CONCEPT_TAG_RULES

# 33차의 별도 안전형 변환기가 실제 생산 계획에서는 어떤 액션으로
# 선택되는지 보존한다. 태그의 오래된 공개 액션명은 변경하지 않는다.
EXPECTED_ACTIONS = {
    "딕셔너리 컴프리헨션": "create_safe_dict_comprehension",
    "리스트 누적 방식 사용": "create_safe_append_collection",
    "리스트 컴프리헨션": "create_safe_comprehension_collection",
    "인덱스 기반 반복 사용": "create_index_iteration",
    "인덱싱 중심 구조": "create_index_iteration",
    "직접 반복 사용": "create_direct_iteration",
}

# 33차 기본형과 동일한 패턴의 독립적인 출력이 있는 검증 예제.
# 실행되는 소스는 아래 리터럴만이며 업로드한 사용자 코드는 취급하지 않는다.
TRUSTED_BASIC = {
    "딕셔너리 컴프리헨션": "result = {}\nfor x in [1, 2, 3]:\n    result[x] = x * 2\nprint(result)\n",
    "리스트 누적 방식 사용": "result = [x * 2 for x in [1, 2, 3]]\nprint(result)\n",
    "리스트 컴프리헨션": "result = []\nfor item in [1, 2, 3]:\n    result.append(item * 2)\nprint(result)\n",
    "인덱스 기반 반복 사용": "values = [1, 2]\nfor item in values:\n    print(item)\n",
    "인덱싱 중심 구조": "values = [1, 2]\nfor item in values:\n    print(item)\n",
    "직접 반복 사용": "values = [10, 20, 30]\nfor i in range(len(values)):\n    print(values[i])\n",
}


def fixture_diff(tags: tuple[str, ...] | list[str] | str) -> dict:
    """Construct just the *already-computed* comparison result; no UI changes.

    Separates plan/applicator/validator correctness from persistence and tag
    extraction. This is not a full style-save -> analysis integration test.
    """
    if isinstance(tags, str):
        tags = (tags,)
    syntax = set(tags) & set(SYNTAX_TAG_RULES)
    concept = set(tags) & set(CONCEPT_TAG_RULES)
    return {
        "missing_syntax_tags": [{"tag": tag} for tag in tags if tag in syntax],
        "missing_concept_tags": [{"tag": tag} for tag in tags if tag in concept and tag not in syntax],
        "style_syntax_names": syntax,
        "style_concept_names": concept,
        "target_syntax_names": set(),
        "target_concept_names": set(),
        "style_metrics": {},
        "target_analysis": {"metrics": {}},
    }


def probe_pipeline(tag: str, source: str) -> dict:
    """Audit a selected action, direct applicator and real strict rollback path."""
    if tag not in EXPECTED_ACTIONS:
        raise KeyError(tag)
    expected = EXPECTED_ACTIONS[tag]
    diff = fixture_diff(tag)
    plan = build_transform_plan(diff)
    actions = plan.get("actions", [])
    selected = [row for row in actions if row.get("tag") == tag]
    chosen = selected[0].get("action") if len(selected) == 1 else None
    dispatcher = _get_transform_function(chosen) if isinstance(chosen, str) else None
    result = {
        "tag": tag,
        "legacy_public_action": CREATE_ACTION_BY_TAG.get(tag),
        "expected_selected_action": expected,
        "selected_action": chosen,
        "selected_action_matches_expected": chosen == expected,
        "selected_action_is_registered": callable(dispatcher),
        "planned_action_count": len(actions),
        "direct_action_status": "not_attempted",
        "direct_source_changed": False,
        "direct_python_valid": False,
        "strict_pipeline_changed": False,
        "strict_pipeline_verdict": "not_attempted",
        "strict_pipeline_original_kept": True,
        "strict_pipeline_applied_note": False,
        "errors": [],
    }
    if chosen != expected or not callable(dispatcher) or len(actions) != 1:
        result["errors"].append("선택 액션이 예상한 실제 경로와 다릅니다.")
        return result
    try:
        transformed, ledger = _apply_style_action(
            code=source,
            action_item=selected[0],
            applied_rules=[],
            warnings=[],
        )
        result["direct_action_status"] = str(ledger.get("status"))
        result["direct_source_changed"] = transformed != source
        ast.parse(transformed)
        result["direct_python_valid"] = True
    except Exception as exc:
        result["errors"].append("개별 액션 실행 예외: " + type(exc).__name__)
        return result
    if result["direct_action_status"] != "applied" or not result["direct_source_changed"]:
        result["errors"].append("선택된 액션이 안전한 기본형에서 코드 변경을 하지 않았습니다.")
        return result
    try:
        # The real planner/applicator/runtime verifier run unchanged. Only the
        # upstream persisted-style comparison input is controlled for this test.
        with patch("app.services.style_apply_service.compare_style_with_target_code", return_value=diff), \
             patch("app.services.style_apply_service.compare_after_transform", return_value={
                 "missing_syntax_tags": [], "missing_concept_tags": [],
             }):
            code_out, summary, applied, warnings, final_diff, verified = apply_coding_style(
                code=source, style={}, strict_runtime_validation=True
            )
        result["strict_pipeline_changed"] = code_out != source
        result["strict_pipeline_original_kept"] = code_out == source
        result["strict_pipeline_applied_note"] = any("적용 완료" in msg for msg in applied)
        result["strict_pipeline_verdict"] = (
            str(verified.get("status")) if isinstance(verified, dict) else "missing_verdict"
        )
        ast.parse(code_out)
        if result["strict_pipeline_changed"] and result["strict_pipeline_verdict"] != "equivalent":
            result["errors"].append("엄격 검증 결과 없이 코드 변경을 유지했습니다.")
        if not result["strict_pipeline_changed"]:
            result["errors"].append("기본형에서 엄격 검증 뒤 변경된 코드가 남지 않았습니다.")
        if result["strict_pipeline_verdict"] != "equivalent":
            result["errors"].append("엄격 검증에서 실행 동등성을 확인하지 못했습니다.")
        if not result["strict_pipeline_applied_note"]:
            result["errors"].append("실제 적용 기록이 남지 않았습니다.")
    except Exception as exc:
        result["errors"].append("실제 적용 서비스 예외: " + type(exc).__name__)
    return result


def audit() -> dict:
    prior = previous.audit()
    issues = list(prior["issues"])
    rows = []
    for tag, source in TRUSTED_BASIC.items():
        item = probe_pipeline(tag, source)
        rows.append(item)
        for error in item["errors"]:
            issues.append(f"{tag}: {error}")
    summary = {
        "all_tags": prior["summary"]["tags"],
        "linked_tags": prior["summary"]["linked"],
        "earlier_either_observed_tags": prior["summary"]["either_tested_transformer_observed_tags"],
        "crosschecked_tags": len(rows),
        "expected_plan_routes": sum(r["selected_action_matches_expected"] for r in rows),
        "registered_plan_routes": sum(r["selected_action_is_registered"] for r in rows),
        "real_action_applied": sum(r["direct_action_status"] == "applied" for r in rows),
        "strict_runtime_equivalent": sum(r["strict_pipeline_verdict"] == "equivalent" for r in rows),
        "strict_final_code_changed": sum(r["strict_pipeline_changed"] for r in rows),
        "issues": len(issues),
    }
    return {
        "summary": summary,
        "six_tag_end_to_end": rows,
        "issues": issues,
        "methodology": {
            "source": "고정된 6개 출력형 코드와 앞 차수의 대표 테스트; 사용자 입력은 실행하지 않음",
            "scope": "이미 계산된 스타일 diff를 지정하여 계획->액션->엄격 검증까지 측정",
            "missing": "실제 저장 및 실제 스타일 비교 파이프라인은 이 감사에서 검증하지 않음",
            "caveat": "출력형 대표 사례의 실행 동등성일 뿐 모든 입력/부작용에 대한 증명은 아님",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit()
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        s = report["summary"]
        print("=== 34차 6태그 실제 스타일 적용 경로·엄격 검증 감사 ===")
        print(f"태그 연결 {s['linked_tags']}/{s['all_tags']}")
        print(f"33차 교차 관측 {s['earlier_either_observed_tags']}/{s['all_tags']}")
        print(f"스타일 계획의 올바른 액션 선택 {s['expected_plan_routes']}/{s['crosschecked_tags']}")
        print(f"실제 변환기 연결 {s['registered_plan_routes']}/{s['crosschecked_tags']}")
        print(f"실제 액션 적용 성공 {s['real_action_applied']}/{s['crosschecked_tags']}")
        print(f"엄격 실행 동등성 확인 {s['strict_runtime_equivalent']}/{s['crosschecked_tags']}")
        print(f"엄격 검증 후 변경된 코드 유지 {s['strict_final_code_changed']}/{s['crosschecked_tags']}")
        for item in report["six_tag_end_to_end"]:
            print(f"- {item['tag']}: 공개={item['legacy_public_action']}, "
                  f"선택={item['selected_action']}, 적용={item['direct_action_status']}, "
                  f"엄격={item['strict_pipeline_verdict']}")
        print(f"감사 오류 {s['issues']}건")
        for issue in report["issues"][:12]:
            print("검사 오류:", issue)
        if not args.output:
            print("태그별 상세 보고서: --output backend/batch34_audit.json (선택)")
    return 0 if (
        s["issues"] == 0
        and s["all_tags"] == s["linked_tags"] == s["earlier_either_observed_tags"] == 102
        and s["crosschecked_tags"] == s["expected_plan_routes"] == s["registered_plan_routes"]
        == s["real_action_applied"] == s["strict_runtime_equivalent"]
        == s["strict_final_code_changed"] == 6
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
