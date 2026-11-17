"""Apply Batch 35-3 diagnostics hooks to the two existing service files.

Run from repository root:
    python backend/tools/apply_batch35_3.py --check
    python backend/tools/apply_batch35_3.py --apply

No production transform implementation, action policy, or six-value return shape
is changed. The script refuses unknown source layouts instead of guessing.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "backend/app/services/style_transform_plan_service.py"
APPLY = ROOT / "backend/app/services/style_apply_service.py"

ORIGINAL_PLAN_END = '''    # CAPSTONE_BATCH28_PLAN_FINALIZE_V1: tag-specific policy IDs and shared-engine
    # deduplication only after legacy direction/conflict resolution completes.
    # Public action strings and compare-only semantics are unchanged.
    return {
        "actions": finalize_tag_action_policies(
            _resolve_new_family_actions(_resolve_iteration_actions(
                _resolve_dictionary_actions(_resolve_collection_actions(finalize_tag_action_policies(actions)))
            ))
        ),
        "compare_only": sorted(set(compare_only)),
    }'''

NEW_PLAN_END = '''    # CAPSTONE_BATCH35_3_REASON_TRACE_V1: observe existing resolver stages.
    # Resolver order, action order, and conflict behavior remain unchanged.
    selected = finalize_tag_action_policies(actions)
    omitted_actions = trace_plan_filter(actions, selected, "policy_initial")
    for stage_name, resolver in (
        ("collection", _resolve_collection_actions),
        ("dictionary", _resolve_dictionary_actions),
        ("iteration", _resolve_iteration_actions),
        ("bidirectional_families", _resolve_new_family_actions),
    ):
        resolved = resolver(selected)
        omitted_actions.extend(trace_plan_filter(selected, resolved, stage_name))
        selected = resolved
    final_actions = finalize_tag_action_policies(selected)
    omitted_actions.extend(trace_plan_filter(selected, final_actions, "policy_final"))
    compare_tags = sorted(set(compare_only))
    compare_details = []
    for tag in compare_tags:
        unmapped = get_create_action_for_tag(tag) is None
        compare_details.append({
            "tag": tag,
            "reason_code": "no_registered_transformer" if unmapped else "insufficient_preference_evidence",
            "reason": (
                "해당 태그에 등록된 자동 변환 액션이 없습니다."
                if unmapped else
                "변환 액션은 등록되어 있지만 적용 방향을 결정할 명시적 스타일 근거가 부족합니다."
            ),
        })
    # Some metric-gated tags are deliberately never proposed as actions.
    # Record their non-selection separately rather than implying an attempt.
    explained_tags = ({item.get("tag") for item in final_actions}
                      | {item.get("tag") for item in omitted_actions}
                      | set(compare_tags))
    not_selected_tags = []
    for item in [*missing_syntax_tags, *missing_concept_tags]:
        tag = _get_tag_name(item)
        if tag and tag not in explained_tags and not any(
            row["tag"] == tag for row in not_selected_tags
        ):
            not_selected_tags.append({
                "tag": tag,
                "status": "not_selected",
                "reason_code": "selection_conditions_unmet",
                "reason": "태그만으로 자동 변환하지 않으며, 저장 메트릭·대상 형태·우선순위 조건을 충족하는 액션이 선택되지 않았습니다.",
            })
    return {
        "actions": final_actions,
        "compare_only": compare_tags,
        "compare_only_details": compare_details,
        "omitted_actions": omitted_actions,
        "not_selected_tags": not_selected_tags,
    }'''

PLAN_IMPORT = "from app.services.style_tag_action_policy_service import finalize_tag_action_policies"
APPLY_IMPORT = "from app.services.style_transform_plan_service import build_transform_plan"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one source anchor, found {count}. No files changed.")
    return source.replace(old, new, 1)


def patch_plan(source: str) -> str:
    source = replace_once(
        source, PLAN_IMPORT,
        PLAN_IMPORT + "\nfrom app.services.style_action_diagnostic_service import trace_plan_filter",
        "plan import",
    )
    # Use the known Batch28 footer, not a regex matching arbitrary code.
    return replace_once(source, ORIGINAL_PLAN_END, NEW_PLAN_END, "plan finalization")


def patch_apply(source: str) -> str:
    source = replace_once(
        source, APPLY_IMPORT,
        APPLY_IMPORT + "\nfrom app.services.style_action_diagnostic_service import build_transform_diagnostics",
        "apply import",
    )
    source = replace_once(
        source,
        '    result = {"tag": tag_name, "action": action, "status": ""}',
        '    result = {"tag": tag_name, "action": action, "status": ""}\n'
        '    # CAPSTONE_BATCH35_3_PLAN_REASON_V1: preserve plan-selection context.\n'
        '    if isinstance(reason, str) and reason:\n'
        '        result["plan_reason"] = reason',
        "action result",
    )
    source = replace_once(
        source,
        '    final_diff = compare_after_transform(style=style, transformed_code=transformed_code)',
        '    final_diff = compare_after_transform(style=style, transformed_code=transformed_code)\n'
        '    # CAPSTONE_BATCH35_3_FINAL_DIAGNOSTICS_V1: additive detail in final_diff.\n'
        '    final_diff["transform_diagnostics"] = build_transform_diagnostics(\n'
        '        transform_plan, action_results, execution_verification\n'
        '    )',
        "final diff",
    )
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Validate patches without writing")
    mode.add_argument("--apply", action="store_true", help="Install the diagnostic hooks")
    args = parser.parse_args()
    original_bytes = {path: path.read_bytes() for path in (PLAN, APPLY)}
    original = {path: content.decode("utf-8").replace("\r\n", "\n")
                for path, content in original_bytes.items()}
    newline = {path: "\r\n" if b"\r\n" in original_bytes[path] else "\n"
               for path in (PLAN, APPLY)}
    already = {
        PLAN: "CAPSTONE_BATCH35_3_REASON_TRACE_V1" in original[PLAN],
        APPLY: "CAPSTONE_BATCH35_3_FINAL_DIAGNOSTICS_V1" in original[APPLY],
    }
    if all(already.values()):
        print("Batch 35-3 already applied; no changes needed.")
        return 0
    if any(already.values()):
        raise RuntimeError("Partial Batch 35-3 installation detected; refusing to modify files.")
    patched = {
        PLAN: patch_plan(original[PLAN]),
        APPLY: patch_apply(original[APPLY]),
    }
    for path, code in patched.items():
        ast.parse(code, filename=str(path))
        compile(code, str(path), "exec")
    diagnostic = ROOT / "backend/app/services/style_action_diagnostic_service.py"
    if not diagnostic.is_file():
        raise RuntimeError("Missing Batch35-3 diagnostic service in extracted ZIP.")
    ast.parse(diagnostic.read_text(encoding="utf-8"), filename=str(diagnostic))
    if args.check:
        print("Batch 35-3 hooks compatible with the current sources (dry run OK).")
        return 0
    written = []
    try:
        for path, code in patched.items():
            path.write_bytes(code.replace("\n", newline[path]).encode("utf-8"))
            written.append(path)
    except Exception:
        for path in written:
            path.write_bytes(original_bytes[path])
        raise
    print("Batch 35-3 installed: transform plan diagnostics and final_diff reporting.")
    print("Changed: backend/app/services/style_transform_plan_service.py")
    print("Changed: backend/app/services/style_apply_service.py")
    print("No existing transformer action mappings or saved metric definitions changed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, SyntaxError) as error:
        print("Batch 35-3 patch aborted:", error, file=sys.stderr)
        sys.exit(1)
