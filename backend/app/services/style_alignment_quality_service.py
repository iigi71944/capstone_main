"""Batch36-5: independent, evidence-only coding-style alignment assessment.

This module does not transform Python code, execute user programs, or infer
semantic equivalence. It separates tag presence from metric-specific surface
preferences. 'equivalent' means the execution verifier observed equality for
its configured test inputs only. Missing / malformed / legacy metrics never
become zero-valued evidence.
"""
from __future__ import annotations

from typing import Any

QUALITY_VERSION = 1
_PREFERENCES = (
    ("sorted", "sorted_reverse_false_explicit_count", "sorted_reverse_false_implicit_count"),
    ("strip", "strip_none_explicit_count", "strip_none_implicit_count"),
)


def _names(diff: dict, field: str) -> set[tuple[str, str]]:
    items = diff.get(field, []) if isinstance(diff, dict) else []
    if not isinstance(items, list):
        return set()
    family = "syntax" if "syntax" in field else "concept"
    return {(family, entry["tag"]) for entry in items
            if isinstance(entry, dict) and isinstance(entry.get("tag"), str)
            and entry["tag"]}


def _missing(diff: dict) -> set[tuple[str, str]]:
    return _names(diff, "missing_syntax_tags") | _names(diff, "missing_concept_tags")


def _nonnegative_int(table: dict, field: str) -> int | None:
    value = table.get(field) if isinstance(table, dict) else None
    return value if type(value) is int and value >= 0 else None


def _metric_evidence(initial_diff: dict, final_diff: dict) -> dict:
    info = initial_diff.get("style_metrics_info", {})
    if (not isinstance(info, dict) or info.get("status") != "current_complete"
            or info.get("stored_version") != 1
            or info.get("automatic_transforms_allowed") is not True):
        return {"status": "unavailable", "evaluated": 0, "improved": 0,
                "regressed": 0, "unchanged": 0, "details": []}
    stored = initial_diff.get("style_metrics", {})
    old = initial_diff.get("target_analysis", {})
    new = final_diff.get("target_analysis", {})
    before = old.get("metrics", {}) if isinstance(old, dict) else {}
    after = new.get("metrics", {}) if isinstance(new, dict) else {}
    details = []
    for family, explicit, implicit in _PREFERENCES:
        counts = tuple(_nonnegative_int(m, k)
                       for m, k in ((stored, explicit), (stored, implicit),
                                    (before, explicit), (before, implicit),
                                    (after, explicit), (after, implicit)))
        if any(value is None for value in counts):
            continue
        s_exp, s_imp, b_exp, b_imp, a_exp, a_imp = counts
        if s_exp == s_imp or s_exp + s_imp == 0:
            continue  # No observed directional preference.
        desired = "explicit" if s_exp > s_imp else "implicit"
        old_opposite = b_imp if desired == "explicit" else b_exp
        new_opposite = a_imp if desired == "explicit" else a_exp
        if old_opposite == 0 and new_opposite == 0:
            continue  # There is no opposite-form opportunity to judge.
        outcome = ("improved" if new_opposite < old_opposite else
                   "regressed" if new_opposite > old_opposite else "unchanged")
        details.append({
            "family": family, "preferred_form": desired,
            "opposite_before": old_opposite, "opposite_after": new_opposite,
            "status": outcome,
        })
    return {"status": "assessed", "evaluated": len(details),
            "improved": sum(d["status"] == "improved" for d in details),
            "regressed": sum(d["status"] == "regressed" for d in details),
            "unchanged": sum(d["status"] == "unchanged" for d in details),
            "details": details}


def build_style_alignment_quality(
    *, initial_diff: dict, final_diff: dict,
    execution_verification: dict | None,
    code_changed: bool,
) -> dict[str, Any]:
    """Return additive, JSON-safe observations; never modify input dicts.

    A metric preference is intentionally not a syntax/concept tag, and an
    introduced tag gap is not necessarily a regression in user preference.
    """
    if not isinstance(initial_diff, dict) or not isinstance(final_diff, dict):
        raise TypeError("Initial and final style comparisons must be mappings")
    before, after = _missing(initial_diff), _missing(final_diff)
    resolved, introduced = before - after, after - before
    metrics = _metric_evidence(initial_diff, final_diff)
    status = (execution_verification.get("status")
              if isinstance(execution_verification, dict) else "not_run")
    equivalent = (execution_verification.get("equivalent")
                  if isinstance(execution_verification, dict) else None)
    observed_verified = status == "equivalent" and equivalent is True
    if not code_changed:
        conclusion = "unchanged"
    elif not observed_verified:
        conclusion = "changed_not_verified"
    elif resolved or metrics["improved"]:
        conclusion = "verified_observed_progress"
    else:
        conclusion = "verified_change_without_measured_progress"
    def serialize(rows):
        return [{"family": kind, "tag": name} for kind, name in sorted(rows)]
    return {
        "version": QUALITY_VERSION,
        "scope": "style_apply_service_pre_formatting",
        "code_changed": bool(code_changed),
        "execution_status": status if isinstance(status, str) else "unknown",
        "observed_runtime_equivalent": observed_verified if code_changed else None,
        "conclusion": conclusion,
        "tag_gap": {
            "before": len(before), "after": len(after),
            "resolved_count": len(resolved),
            "introduced_count": len(introduced),
            "resolved": serialize(resolved), "introduced": serialize(introduced),
            "remaining": serialize(after),
        },
        "default_form_preferences": metrics,
        "limitations": [
            "Tag presence counts do not prove the saved style is fully reproduced.",
            "Default-form metrics are evaluated separately from syntax/concept tags.",
            "Observed runtime equivalence is restricted to the executed test inputs.",
        ],
    }


__all__ = ["build_style_alignment_quality", "QUALITY_VERSION"]
