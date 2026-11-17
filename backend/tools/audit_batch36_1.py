"""Batch 36-1: observational evaluation of 50 realistic style-application cases.

Does not modify production code, tags, saved styles, or transformer policies.
Usage (from backend working directory):
    python tools/audit_batch36_1.py --output batch36_1_audit.json
    python tools/audit_batch36_1.py --group signature --limit 3
    python tools/audit_batch36_1.py --list

This is a deterministic curated benchmark, NOT real customer code or a formal
proof of Python program equivalence. Runtime checks are those already provided
by the existing style engine. 'not_verified' is never counted as equivalent.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from difflib import unified_diff
from hashlib import sha256
import json
from pathlib import Path
import sys

from tools.batch36_1_cases import CASES, Case

REPORT_VERSION = 1


def _sha(source: str) -> str:
    return sha256(source.encode("utf-8")).hexdigest()


def _syntax_valid(source: str) -> bool:
    import ast
    try:
        ast.parse(source)
        return True
    except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError):
        return False


def _tag_names(items) -> set[str]:
    if not isinstance(items, list):
        return set()
    return {item["tag"] for item in items if isinstance(item, dict)
            and isinstance(item.get("tag"), str) and item["tag"]}


def _missing(diff: dict) -> set[str]:
    return (_tag_names(diff.get("missing_syntax_tags", []))
            | _tag_names(diff.get("missing_concept_tags", [])))


def _diff_excerpt(before: str, after: str, limit=4000) -> str:
    if before == after:
        return ""
    excerpt = "".join(unified_diff(before.splitlines(keepends=True),
                                    after.splitlines(keepends=True),
                                    fromfile="target.py", tofile="transformed.py"))
    return excerpt[:limit] + ("\n... truncated ..." if len(excerpt) > limit else "")


def _optional_real_services(analyze_fn, compare_fn, apply_fn):
    if analyze_fn is None:
        from app.services.style_diff_service import analyze_code_style
        analyze_fn = analyze_code_style
    if compare_fn is None:
        from app.services.style_diff_service import compare_style_with_target_code
        compare_fn = compare_style_with_target_code
    if apply_fn is None:
        from app.services.style_apply_service import apply_coding_style
        apply_fn = apply_coding_style
    return analyze_fn, compare_fn, apply_fn


def evaluate_case(case: Case, *, strict_runtime_validation: bool = False,
                  analyze_fn=None, compare_fn=None, apply_fn=None) -> dict:
    """Evaluate the actual engine via dependency-injected, read-only calls."""
    result = {
        "id": case.case_id, "group": case.group, "name": case.name,
        "purpose": case.purpose, "stored_version_mode": case.version,
        "saved_source_sha256": _sha(case.style_code),
        "target_sha256": _sha(case.target_code),
        "input_syntax_valid": (_syntax_valid(case.style_code)
                               and _syntax_valid(case.target_code)),
        "errors": [],
    }
    if not result["input_syntax_valid"]:
        result["errors"].append("invalid_fixture_python")
        return result

    try:
        analyze_fn, compare_fn, apply_fn = _optional_real_services(
            analyze_fn, compare_fn, apply_fn)
        analysis = analyze_fn(case.style_code)
        style_metrics = analysis["metrics"]
        # Real style creation uses full metrics + current schema version.
        # Test-only cases explicitly exercise an unchanged legacy record.
        style = {
            "id": case.case_id,
            "name": case.name,
            "description": "Batch36-1 benchmark fixture",
            "created_at": "2026-11-17T00:00:00Z",
            "syntax_tags": analysis["syntax_tags"],
            "concept_tags": analysis["concept_tags"],
            "metrics": dict(style_metrics),
        }
        if case.version == "v1":
            style["metrics_version"] = 1
        elif case.version != "legacy":
            raise ValueError("Unsupported fixture version: " + str(case.version))

        before = compare_fn(style, case.target_code)
        before_missing = _missing(before)
        kwargs = {"code": case.target_code, "style": style,
                  "strict_runtime_validation": strict_runtime_validation}
        if case.stdin is not None:
            kwargs["stdin"] = case.stdin
        response = apply_fn(**kwargs)
        if not isinstance(response, (tuple, list)) or len(response) != 6:
            raise ValueError("style_apply_return_contract_mismatch")
        transformed, summary, applied_rules, warnings, final_diff, verification = response
        if not isinstance(transformed, str) or not isinstance(final_diff, dict):
            raise ValueError("invalid_style_apply_output")

        after_missing = _missing(final_diff)
        resolved = sorted(before_missing - after_missing)
        introduced = sorted(after_missing - before_missing)
        diagnostics = final_diff.get("transform_diagnostics", {})
        if not isinstance(diagnostics, dict):
            diagnostics = {}
        counts = diagnostics.get("counts") if isinstance(diagnostics.get("counts"), dict) else {}
        omitted = diagnostics.get("omitted_actions", [])
        attempted = diagnostics.get("attempted_actions", [])
        verification_status = (verification.get("status", "unknown")
                               if isinstance(verification, dict) else "not_run")
        verification_equivalent = (verification.get("equivalent")
                                   if isinstance(verification, dict) else None)
        changed = transformed != case.target_code
        python_valid = _syntax_valid(transformed)
        result.update({
            "changed": changed,
            "output_syntax_valid": python_valid,
            "transformed_sha256": _sha(transformed),
            "verification_status": verification_status,
            "verification_equivalent": verification_equivalent,
            "initial_missing_tags": sorted(before_missing),
            "final_missing_tags": sorted(after_missing),
            "resolved_tags": resolved,
            "introduced_missing_tags": introduced,
            "initial_missing_count": len(before_missing),
            "resolved_count": len(resolved),
            "introduced_count": len(introduced),
            "tag_progress_rate": (round(len(resolved) / len(before_missing), 4)
                                  if before_missing else None),
            "action_diagnostic_counts": counts,
            "attempt_statuses": dict(Counter(
                str(a.get("status", "unknown")) for a in attempted
                if isinstance(a, dict))),
            "omitted_reason_codes": dict(Counter(
                str(a.get("reason_code", "unknown")) for a in omitted
                if isinstance(a, dict))),
            "not_selected_reason_codes": dict(Counter(
                str(a.get("reason_code", "unknown"))
                for a in diagnostics.get("not_selected_tags", [])
                if isinstance(a, dict))),
            "warnings": [str(w) for w in warnings] if isinstance(warnings, list) else [],
            "applied_rule_count": len(applied_rules) if isinstance(applied_rules, list) else 0,
            "diff_excerpt": _diff_excerpt(case.target_code, transformed),
            "snapshot_status": ((before.get("style_metrics_info") or {}).get("status")
                                if isinstance(before.get("style_metrics_info"), dict)
                                else None),
        })
        if not python_valid:
            result["errors"].append("invalid_transformed_python")
        if verification_status == "different" and changed:
            result["errors"].append("known_runtime_difference_not_rolled_back")
        if strict_runtime_validation and changed and verification_status != "equivalent":
            result["errors"].append("strict_mode_unverified_change")
        if verification_status == "equivalent" and verification_equivalent is not True:
            result["errors"].append("contradictory_equivalent_verdict")
        if verification_status == "different" and verification_equivalent is not False:
            result["errors"].append("contradictory_difference_verdict")
        if verification_status == "not_verified" and verification_equivalent is not None:
            result["errors"].append("contradictory_unverified_verdict")
    except Exception as exc:
        result["errors"].append("case_exception:" + type(exc).__name__ + ": " + str(exc)[:300])
    return result


def summarize(results: list[dict]) -> dict:
    """Explicit denominators prevent counting skipped/no-op as success."""
    total = len(results)
    changed = [r for r in results if r.get("changed") is True]
    verifiable = [r for r in changed if r.get("verification_status") == "equivalent"
                  and r.get("verification_equivalent") is True]
    not_verified = [r for r in changed if r.get("verification_status") == "not_verified"]
    with_gap = [r for r in results if r.get("initial_missing_count", 0) > 0]
    initial_missing = sum(r.get("initial_missing_count", 0) for r in results)
    resolved = sum(r.get("resolved_count", 0) for r in results)
    introduced = sum(r.get("introduced_count", 0) for r in results)
    failed = [r for r in results if r.get("errors")]
    omissions = Counter()
    attempted = Counter()
    not_selected = Counter()
    groups: dict[str, dict] = {}
    verification = Counter()
    for r in results:
        verification.update([str(r.get("verification_status", "not_evaluated"))])
        group = r.get("group", "unknown")
        row = groups.setdefault(group, {"total": 0, "changed": 0, "verified_changes": 0, "errors": 0})
        row["total"] += 1
        row["changed"] += int(r.get("changed") is True)
        row["verified_changes"] += int(r in verifiable)
        row["errors"] += int(bool(r.get("errors")))
        omissions.update(r.get("omitted_reason_codes", {}))
        attempted.update(r.get("attempt_statuses", {}))
        not_selected.update(r.get("not_selected_reason_codes", {}))
    return {
        "total_cases": total,
        "cases_with_no_initial_style_gap": total - len(with_gap),
        "cases_with_initial_style_gap": len(with_gap),
        "changed_cases": len(changed),
        "unchanged_cases": total - len(changed),
        "changed_and_runtime_equivalent": len(verifiable),
        "changed_but_runtime_not_verified": len(not_verified),
        "changed_with_other_verification": len(changed) - len(verifiable) - len(not_verified),
        "runtime_verified_change_rate": (round(len(verifiable) / len(changed), 4)
                                         if changed else None),
        "observed_missing_tag_instances_before": initial_missing,
        "resolved_missing_tag_instances": resolved,
        "newly_missing_tag_instances": introduced,
        "resolved_missing_tag_rate": (round(resolved / initial_missing, 4)
                                      if initial_missing else None),
        "failed_case_count": len(failed),
        "failed_case_ids": [r["id"] for r in failed],
        "verification_status_counts": dict(verification),
        "attempt_status_counts": dict(attempted),
        "omission_reason_counts": dict(omissions),
        "not_selected_reason_counts": dict(not_selected),
        "by_group": groups,
    }


def run_audit(cases: list[Case], *, strict_runtime_validation: bool = False,
              analyze_fn=None, compare_fn=None, apply_fn=None) -> dict:
    results = [evaluate_case(case, strict_runtime_validation=strict_runtime_validation,
                             analyze_fn=analyze_fn, compare_fn=compare_fn, apply_fn=apply_fn)
               for case in cases]
    return {
        "report_version": REPORT_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_origin": "authored deterministic real-world-like fixtures; not external project samples",
        "scope": "backend app.services.style_apply_service only; no UI, formatting, or broad behavioral proof",
        "strict_runtime_validation": strict_runtime_validation,
        "case_count": len(cases),
        "python_version": sys.version.split()[0],
        "summary": summarize(results),
        "cases": results,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Batch36-1: evaluate 50 curated Python style pairs")
    parser.add_argument("--output", default="batch36_1_audit.json",
                        help="Report path relative to current working directory")
    parser.add_argument("--group", help="Run only one of 10 groups")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--strict-runtime", action="store_true",
                        help="Enable existing opt-in runtime rollback on uncertain verdicts")
    parser.add_argument("--list", action="store_true", help="Print fixture names; do not execute")
    args = parser.parse_args(argv)
    chosen = [case for case in CASES if args.group is None or case.group == args.group]
    if args.group is not None and not chosen:
        parser.error("Unknown group: " + args.group)
    if args.limit is not None:
        if args.limit < 1:
            parser.error("--limit must be >= 1")
        chosen = chosen[:args.limit]
    if args.list:
        for case in chosen:
            print(f"{case.case_id} [{case.group}] {case.name}")
        print(f"총 {len(chosen)}개")
        return 0

    report = run_audit(chosen, strict_runtime_validation=args.strict_runtime)
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = report["summary"]
    print("=== Batch36-1 실제 사용 상황 모사 코드 자동 평가 ===")
    print("총 사례:", summary["total_cases"], "/ 코드 변경:", summary["changed_cases"],
          "/ 변경 없음:", summary["unchanged_cases"])
    print("실행 동등성 확인된 변경:", summary["changed_and_runtime_equivalent"],
          "/ 변경 후 검증 불가:", summary["changed_but_runtime_not_verified"])
    print("초기 누락 태그:", summary["observed_missing_tag_instances_before"],
          "/ 해소:", summary["resolved_missing_tag_instances"],
          "/ 새 누락:", summary["newly_missing_tag_instances"])
    print("회귀/검사 위반 사례:", summary["failed_case_count"], summary["failed_case_ids"])
    print("보고서:", dest)
    return 0 if summary["failed_case_count"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
