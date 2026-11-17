"""Install Batch35-5 plan refinements without overwriting unrelated code.

From the capstone_main root (after unzipping):
    python backend/tools/apply_batch35_5.py --check
    python backend/tools/apply_batch35_5.py --apply

Only modifies the existing style_transform_plan_service.py. The new pure
refinement service and test file are installed by extracting the ZIP.
Requires Batch35-3 and Batch35-4; no schema, UI, or transformer changes.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "backend/app/services/style_transform_plan_service.py"
SERVICE = ROOT / "backend/app/services/style_metric_refinement_service.py"
MARKER = "CAPSTONE_BATCH35_5_METRIC_REFINEMENT_V1"


def replace_once(source: str, before: str, after: str, label: str) -> str:
    count = source.count(before)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}; no changes written")
    return source.replace(before, after, 1)


def patch_plan(source: str) -> str:
    if "CAPSTONE_BATCH35_3_REASON_TRACE_V1" not in source:
        raise RuntimeError("Batch35-3 diagnostics are required")
    if "CAPSTONE_BATCH35_4_METRIC_VERSION_V1" not in source:
        raise RuntimeError("Batch35-4 versioned metrics are required")
    source = replace_once(
        source,
        "from app.services.style_tag_action_policy_service import finalize_tag_action_policies",
        "from app.services.style_tag_action_policy_service import finalize_tag_action_policies\n"
        "# " + MARKER + ": versioned metric-based action refinements.\n"
        "from app.services.style_metric_refinement_service import (\n"
        "    add_dominant_default_actions,\n"
        "    refine_closed_pattern_actions,\n"
        ")",
        "refinement import",
    )
    source = replace_once(
        source,
        "    # CAPSTONE_BATCH35_3_REASON_TRACE_V1: observe existing resolver stages.",
        "    # " + MARKER + ": add strongly preferred default forms.\n"
        "    # Legacy and incomplete metric snapshots keep their old behavior.\n"
        "    actions = add_dominant_default_actions(diff, actions)\n\n"
        "    # CAPSTONE_BATCH35_3_REASON_TRACE_V1: observe existing resolver stages.",
        "mixed-form selection",
    )
    source = replace_once(
        source,
        '    omitted_actions.extend(trace_plan_filter(selected, final_actions, "policy_final"))\n'
        '    compare_tags = sorted(set(compare_only))',
        '    omitted_actions.extend(trace_plan_filter(selected, final_actions, "policy_final"))\n'
        '    # ' + MARKER + ': check 7 closed-pattern families against observed\n'
        '    # target shape before dispatching; log refusals as omitted actions.\n'
        '    final_actions, metric_omissions = refine_closed_pattern_actions(diff, final_actions)\n'
        '    omitted_actions.extend(metric_omissions)\n'
        '    compare_tags = sorted(set(compare_only))',
        "closed-pattern gate",
    )
    return source


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__)
    mode = args.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parsed = args.parse_args()

    if not PLAN.is_file() or not SERVICE.is_file():
        raise RuntimeError("Expected plan and new refinement module not found in backend/app/services")
    original = PLAN.read_bytes()
    service_text = SERVICE.read_text(encoding="utf-8")
    ast.parse(service_text, filename=str(SERVICE))
    source = original.decode("utf-8").replace("\r\n", "\n")
    if MARKER in source:
        # Refuse a partial installation: a lone marker is insufficient.
        if not all(snippet in source for snippet in (
            "actions = add_dominant_default_actions(diff, actions)",
            "final_actions, metric_omissions = refine_closed_pattern_actions(diff, final_actions)",
        )):
            raise RuntimeError("Partial Batch35-5 installation; inspect the plan file manually")
        print("Batch35-5 is already installed. No changes made.")
        return 0
    patched = patch_plan(source)
    ast.parse(patched, filename=str(PLAN))
    if parsed.check:
        print("Batch35-5 check OK: all previous stage anchors and Python syntax verified; no changes written.")
        return 0
    newline = "\r\n" if b"\r\n" in original else "\n"
    PLAN.write_bytes(patched.replace("\n", newline).encode("utf-8"))
    print("Batch35-5 installed: majority preferences, 7 structural gates, 35-3 reason trace.")
    print("Modified:", PLAN.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, SyntaxError, UnicodeError, RuntimeError) as exc:
        print("Batch35-5 patch aborted:", exc, file=sys.stderr)
        sys.exit(1)
