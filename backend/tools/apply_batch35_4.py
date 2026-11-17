"""Install Batch35-4 metric version handling, without overwriting user changes.

From capstone_main root:
    python backend/tools/apply_batch35_4.py --check
    python backend/tools/apply_batch35_4.py --apply

Requires Batch35-3. Verifies all anchors, Python syntax, and new module presence
before modifying any source. Idempotent and CRLF/LF preserving.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = {
    "diff": ROOT / "backend/app/services/style_diff_service.py",
    "plan": ROOT / "backend/app/services/style_transform_plan_service.py",
    "apply": ROOT / "backend/app/services/style_apply_service.py",
    "schema": ROOT / "backend/app/schemas/style_apply.py",
    "types": ROOT / "frontend/types/analysis.ts",
    "factory": ROOT / "frontend/lib/codingStyleFactory.ts",
}
MARKER = "CAPSTONE_BATCH35_4_METRIC_VERSION_V1"


def once(source: str, old: str, replacement: str, path: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected a unique anchor, found {count}. No changes written.")
    return source.replace(old, replacement, 1)


def patch_diff(s: str) -> str:
    s = once(s,
        "from app.services.metric_service import calculate_metrics",
        "from app.services.metric_service import calculate_metrics\n"
        "from app.services.style_metric_snapshot_service import normalize_style_metric_snapshot",
        "diff import")
    s = once(s,
        "    style_metrics = _get_style_metrics(style)",
        "    # " + MARKER + ": track observed counters without inventing zeros.\n"
        "    style_metrics, style_metrics_info = normalize_style_metric_snapshot(style)",
        "diff metrics")
    return once(s,
        '        "style_metrics": style_metrics,',
        '        "style_metrics": style_metrics,\n'
        '        "style_metrics_info": style_metrics_info,',
        "diff payload")


def patch_plan(s: str) -> str:
    anchor = 'def build_transform_plan(diff: dict) -> dict:\n    missing_syntax_tags = diff.get("missing_syntax_tags", [])'
    replacement = '''def build_transform_plan(diff: dict) -> dict:
    # CAPSTONE_BATCH35_4_METRIC_VERSION_V1: reject unsafe declared snapshots.
    info = diff.get("style_metrics_info", {})
    if isinstance(info, dict) and info.get("automatic_transforms_allowed") is False:
        explanation = (
            "저장 메트릭 버전이 지원되지 않거나, 선언된 버전의 메트릭에 "
            "누락·잘못된 값이 있어 자동 변환을 안전하게 결정할 수 없습니다."
        )
        skipped = []
        known = set()
        for item in [*diff.get("missing_syntax_tags", []),
                     *diff.get("missing_concept_tags", [])]:
            tag = _get_tag_name(item)
            if tag and tag not in known:
                known.add(tag)
                skipped.append({
                    "tag": tag,
                    "status": "not_selected",
                    "reason_code": "untrusted_metric_snapshot",
                    "reason": explanation,
                })
        return {
            "actions": [], "compare_only": [], "compare_only_details": [],
            "omitted_actions": [], "not_selected_tags": skipped,
        }
    missing_syntax_tags = diff.get("missing_syntax_tags", [])'''
    if "CAPSTONE_BATCH35_3_REASON_TRACE_V1" not in s:
        raise RuntimeError("Batch35-3 diagnostics must be applied before Batch35-4.")
    return once(s, anchor, replacement, "plan entry")


def patch_apply(s: str) -> str:
    anchor = '''    initial_diff = compare_style_with_target_code(style=style, code=code)
    transform_plan = build_transform_plan(initial_diff)'''
    replacement = '''    initial_diff = compare_style_with_target_code(style=style, code=code)
    # CAPSTONE_BATCH35_4_METRIC_VERSION_V1: warn when versioned evidence is unsafe.
    metric_info = initial_diff.get("style_metrics_info", {})
    if isinstance(metric_info, dict) and not metric_info.get("automatic_transforms_allowed", True):
        _add_unique(warnings,
                    "저장 메트릭 버전 또는 필수 메트릭 값이 유효하지 않아 "
                    "자동 변환을 생략했습니다. 스타일 비교 결과는 계속 제공됩니다.")
    transform_plan = build_transform_plan(initial_diff)'''
    if "CAPSTONE_BATCH35_3_FINAL_DIAGNOSTICS_V1" not in s:
        raise RuntimeError("Batch35-3 final diagnostics must be applied before Batch35-4.")
    return once(s, anchor, replacement, "apply plan")


def patch_schema(s: str) -> str:
    old = '    metrics: Dict[str, int]\n    created_at: str'
    new = '''    # CAPSTONE_BATCH35_4_METRIC_VERSION_V1: legacy styles may omit metrics.
    # Validation is performed by the version-aware service, not Pydantic int coercion.
    metrics: Dict[str, Any] = Field(default_factory=dict)
    metrics_version: Optional[int] = None
    created_at: str'''
    return once(s, old, new, "saved style schema")


def patch_types(s: str) -> str:
    return once(s,
        '  metrics: Record<string, number>;\n  formatting_style?: Record<string, unknown>;\n  created_at: string;',
        '  metrics: Record<string, number>;\n'
        '  /** ' + MARKER + ': absent for historical saved styles. */\n'
        '  metrics_version?: number;\n'
        '  formatting_style?: Record<string, unknown>;\n  created_at: string;',
        "frontend CodingStyle")


def patch_factory(s: str) -> str:
    return once(s,
        '    metrics: analysis.metrics,\n\n    // CAPSTONE_FORMATTING_STYLE_GIT_ALIGNED_V2',
        '    metrics: analysis.metrics,\n\n'
        '    // ' + MARKER + ': new snapshots explicitly declare the 81-metric schema.\n'
        '    metrics_version: 1,\n\n    // CAPSTONE_FORMATTING_STYLE_GIT_ALIGNED_V2',
        "frontend save builder")

PATCHERS = {
    "diff": patch_diff,
    "plan": patch_plan,
    "apply": patch_apply,
    "schema": patch_schema,
    "types": patch_types,
    "factory": patch_factory,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    originals = {key: path.read_bytes() for key, path in FILES.items()}
    sources = {key: raw.decode("utf-8").replace("\r\n", "\n")
               for key, raw in originals.items()}
    inserted = {key: MARKER in source for key, source in sources.items()}
    if all(inserted.values()):
        print("Batch35-4 already installed; nothing to change.")
        return 0
    if any(inserted.values()):
        raise RuntimeError("Partial Batch35-4 installation detected; refusing to modify files.")
    service = ROOT / "backend/app/services/style_metric_snapshot_service.py"
    if not service.is_file():
        raise RuntimeError("Missing style_metric_snapshot_service.py from ZIP.")
    ast.parse(service.read_text(encoding="utf-8"), filename=str(service))
    patched = {key: PATCHERS[key](source) for key, source in sources.items()}
    for key in ("diff", "plan", "apply", "schema"):
        ast.parse(patched[key], filename=str(FILES[key]))
    if args.check:
        print("Batch35-4 compatibility check passed; no source files changed.")
        return 0
    written = []
    try:
        for key, path in FILES.items():
            newline = "\r\n" if b"\r\n" in originals[key] else "\n"
            path.write_bytes(patched[key].replace("\n", newline).encode("utf-8"))
            written.append(key)
    except Exception:
        for key in written:
            FILES[key].write_bytes(originals[key])
        raise
    print("Batch35-4 installed: versioned metrics, guarded planning, legacy compatibility.")
    for key, path in FILES.items():
        print("Modified:", path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, SyntaxError, UnicodeError) as error:
        print("Batch35-4 patch aborted:", error, file=sys.stderr)
        sys.exit(1)
