"""Read-only registry and saved-style action-plan audit for the capstone app.

This service never executes user code or performs code transformations. It
inspects the actual action dispatcher source and the configured tag registry.

From backend/:
    python -m app.services.style_transform_audit_service
    python -m app.services.style_transform_audit_service --json
    python -m app.services.style_transform_audit_service --diff-json path/to/diff.json
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

from app.services.style_tag_transform_map_service import (
    COMPARE_ONLY_TAGS,
    CREATE_ACTION_BY_TAG,
    PLANNED_FAMILY_PRIORITY,
    PLANNED_TAG_FAMILY,
    get_tag_transform_status,
)
from app.services.style_transform_plan_service import build_transform_plan
from app.services.tag_rule_service import CONCEPT_TAG_RULES, SYNTAX_TAG_RULES

# These are internal action names selected at plan time. They deliberately do
# not replace legacy public mappings, preserving existing saved styles.
INTERNAL_ACTIONS = frozenset({
    "create_safe_append_collection",
    "create_safe_comprehension_collection",
    "create_safe_dict_comprehension",
    "create_safe_dict_loop",
})

ITERATION_TARGET_ACTIONS = frozenset({
    "create_direct_iteration", "create_index_iteration", "create_while_iteration",
})


def _issue(code: str, message: str, *, level: str = "error") -> dict[str, str]:
    return {"level": level, "code": code, "message": message}


def _dispatcher_actions() -> tuple[dict[str, str], list[dict[str, str]]]:
    """Parse the real dispatcher map without importing execution dependencies.

    A successfully parsed name is evidence of a *configured* link, not proof
    that an arbitrary code transform is safe or semantically equivalent.
    """
    path = Path(__file__).with_name("style_apply_service.py")
    issues: list[dict[str, str]] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        return {}, [_issue("DISPATCHER_UNREADABLE", f"액션 연결 파일을 읽을 수 없습니다: {exc}")]

    available_symbols = {
        alias.asname or alias.name
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    } | {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    dispatcher = next(
        (node for node in tree.body
         if isinstance(node, ast.FunctionDef) and node.name == "_get_transform_function"),
        None,
    )
    if dispatcher is None:
        return {}, [_issue("DISPATCHER_MISSING", "_get_transform_function 함수가 없습니다.")]

    candidates = [
        node.value for node in ast.walk(dispatcher)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and isinstance(node.value, ast.Dict)
        and any(isinstance(target, ast.Name) and target.id == "action_map"
                for target in (node.targets if isinstance(node, ast.Assign) else [node.target]))
    ]
    if len(candidates) != 1:
        return {}, [_issue("DISPATCH_MAP_INVALID", "action_map 딕셔너리를 하나만 찾아야 합니다.")]

    found: dict[str, str] = {}
    for key_node, value_node in zip(candidates[0].keys, candidates[0].values):
        if (not isinstance(key_node, ast.Constant)
                or not isinstance(key_node.value, str)
                or not isinstance(value_node, ast.Name)):
            issues.append(_issue("DISPATCH_ENTRY_INVALID", "action_map의 키/값이 정적 문자열/함수명이 아닙니다."))
            continue
        action, symbol = key_node.value, value_node.id
        if action in found:
            issues.append(_issue("DISPATCH_DUPLICATE", f"중복 액션: {action}"))
        found[action] = symbol
        if symbol not in available_symbols:
            issues.append(_issue("DISPATCH_SYMBOL_MISSING", f"{action}의 변환기 {symbol}가 import/정의되어 있지 않습니다."))
    return found, issues


def audit_style_registry() -> dict[str, Any]:
    """Describe tag coverage and verify the static action wiring.

    Covers every tag in SYNTAX_TAG_RULES and CONCEPT_TAG_RULES. This report
    intentionally distinguishes `planned` from the stricter `compare_only`.
    """
    syntax_names = set(SYNTAX_TAG_RULES)
    concept_names = set(CONCEPT_TAG_RULES)
    all_names = syntax_names | concept_names
    issues: list[dict[str, str]] = []
    dispatcher, dispatcher_issues = _dispatcher_actions()
    issues.extend(dispatcher_issues)

    for tag, action in sorted(CREATE_ACTION_BY_TAG.items()):
        if tag not in all_names:
            issues.append(_issue("UNDECLARED_LINKED_TAG", f"등록되지 않은 연결 태그: {tag}"))
        if not isinstance(action, str) or action not in dispatcher:
            issues.append(_issue("LINKED_ACTION_MISSING", f"{tag} -> {action} 액션을 실행 연결 목록에서 찾지 못했습니다."))
    for action in sorted(INTERNAL_ACTIONS):
        if action not in dispatcher:
            issues.append(_issue("INTERNAL_ACTION_MISSING", f"내부 안전 변환 액션이 없습니다: {action}"))
    for tag, family in sorted(PLANNED_TAG_FAMILY.items()):
        if tag not in all_names:
            issues.append(_issue("UNDECLARED_PLANNED_TAG", f"등록되지 않은 개발예정 태그: {tag}"))
        if tag in CREATE_ACTION_BY_TAG:
            issues.append(_issue("PLANNED_LINKED_CONFLICT", f"연결/예정 분류가 중복된 태그: {tag}"))
        if family not in PLANNED_FAMILY_PRIORITY:
            issues.append(_issue("PRIORITY_MISSING", f"{tag}의 예정 분류 우선순위가 없습니다: {family}"))

    expected_compare = all_names - set(CREATE_ACTION_BY_TAG)
    if COMPARE_ONLY_TAGS != expected_compare:
        issues.append(_issue("COMPARE_ONLY_SET_DRIFT", "COMPARE_ONLY_TAGS가 현재 태그 규칙과 불일치합니다."))

    statuses: dict[str, list[str]] = {"linked": [], "planned": [], "compare_only": []}
    for tag in sorted(all_names):
        status = get_tag_transform_status(tag)
        if status not in statuses:
            issues.append(_issue("INVALID_STATUS", f"{tag}의 분류가 잘못되었습니다: {status}"))
            continue
        statuses[status].append(tag)

    summary = {
        "all_tags": len(all_names),
        "syntax_tags": len(syntax_names),
        "concept_tags": len(concept_names),
        "linked_tags": len(statuses["linked"]),
        "planned_tags": len(statuses["planned"]),
        "compare_only_tags": len(statuses["compare_only"]),
        "public_actions": len(set(CREATE_ACTION_BY_TAG.values())),
        "dispatcher_actions": len(dispatcher),
        "issues": len(issues),
    }
    return {
        "status": "ok" if not issues else "issues_found",
        "summary": summary,
        "tag_statuses": statuses,
        "dispatcher": dispatcher,
        "issues": issues,
        "note": "정적 연결 상태 감사입니다. 실제 코드 실행 동등성을 보증하지 않습니다.",
    }


def audit_saved_style_plan(diff: dict[str, Any]) -> dict[str, Any]:
    """Explain selected actions and detect ambiguous iteration preferences.

    `diff` is the dictionary returned by compare_style_with_target_code().
    This runs only plan construction, never user-provided Python source.
    """
    if not isinstance(diff, dict):
        raise TypeError("diff는 스타일 비교 결과 딕셔너리여야 합니다.")
    plan = build_transform_plan(diff)
    missing = []
    for key in ("missing_syntax_tags", "missing_concept_tags"):
        values = diff.get(key, [])
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict) and isinstance(item.get("tag"), str):
                missing.append(item["tag"])

    conflict_warnings = []
    explicit = {CREATE_ACTION_BY_TAG[tag] for tag in missing if tag in CREATE_ACTION_BY_TAG}
    iteration_pref = explicit & ITERATION_TARGET_ACTIONS
    if len(iteration_pref) > 1:
        conflict_warnings.append(
            "저장 스타일에 서로 다른 반복 방식이 동시에 요청되어 "
            "해당 반복 변환은 안전하게 생략했습니다."
        )
    if ("리스트 컴프리헨션" in missing and "리스트 누적 방식 사용" in missing):
        conflict_warnings.append(
            "리스트 누적과 리스트 컴프리헨션을 동시에 요청하여 "
            "리스트 방향 변환을 생략했습니다."
        )

    selected = {item.get("action") for item in plan.get("actions", [])}
    return {
        "selected_actions": plan.get("actions", []),
        "compare_only": plan.get("compare_only", []),
        "conflict_warnings": conflict_warnings,
        "has_actions": bool(selected),
        "note": "계획만 검사했습니다. 실제 변환 실행 여부는 별도 테스트로 확인해야 합니다.",
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="캡스톤 저장 스타일 태그/변환 연결 감사")
    parser.add_argument("--json", action="store_true", help="레지스트리 감사 결과를 JSON으로 출력")
    parser.add_argument("--diff-json", type=Path, metavar="FILE", help="스타일 비교 결과 JSON에 대한 액션 계획 분석")
    args = parser.parse_args()
    registry = audit_style_registry()
    result = registry
    if args.diff_json is not None:
        try:
            loaded = json.loads(args.diff_json.read_text(encoding="utf-8"))
            result = audit_saved_style_plan(loaded)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            parser.error(f"스타일 비교 파일을 읽지 못했습니다: {exc}")

    if args.json or args.diff_json is not None:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        s = registry["summary"]
        print("=== 저장 스타일 태그·변환 감사 ===")
        print(f"전체 {s['all_tags']}개 태그 | 연결 {s['linked_tags']}개 | "
              f"개발예정 {s['planned_tags']}개 | 비교전용 {s['compare_only_tags']}개")
        print(f"공개 액션 {s['public_actions']}종 | 실행 연결 {s['dispatcher_actions']}종")
        print("상태:", "정상" if registry["status"] == "ok" else "문제 발견")
        for issue in registry["issues"]:
            print(f"[{issue['code']}] {issue['message']}")
        print(registry["note"])
    return 0 if registry["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(_main())
