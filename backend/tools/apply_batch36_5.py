"""Apply the narrow Batch36-5 additive quality diagnostic to production.

The ZIP already contains the new pure service, tests and offline audit tools.
Only the two markers in backend/app/services/style_apply_service.py are edited.
Run at the project root: python backend/tools/apply_batch36_5.py --check/--apply
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path

TARGET = Path("backend/app/services/style_apply_service.py")
MARKER = "CAPSTONE_BATCH36_5_ALIGNMENT_QUALITY_V1"
OLD_IMPORT = "from app.services.style_action_diagnostic_service import build_transform_diagnostics\n"
NEW_IMPORT = (OLD_IMPORT + "from app.services.style_alignment_quality_service import (\n"
              "    build_style_alignment_quality,\n)\n")
OLD_BLOCK = (
    "    final_diff[\"transform_diagnostics\"] = build_transform_diagnostics(\n"
    "        transform_plan, action_results, execution_verification\n"
    "    )\n"
)
NEW_BLOCK = (OLD_BLOCK +
    f"    # {MARKER}: independent tag-gap and default-form evidence.\n"
    "    # Does not change any transforms or the six-value return contract.\n"
    "    final_diff[\"style_alignment_quality\"] = build_style_alignment_quality(\n"
    "        initial_diff=initial_diff,\n"
    "        final_diff=final_diff,\n"
    "        execution_verification=execution_verification,\n"
    "        code_changed=_is_changed(code, transformed_code),\n"
    "    )\n"
)


def patch(source: bytes) -> tuple[bytes, str]:
    if not isinstance(source, bytes):
        raise TypeError("Expected source bytes")
    text = source.decode("utf-8")
    normalized = text.replace("\r\n", "\n")
    if MARKER in normalized:
        if (normalized.count(MARKER) == 1 and normalized.count(NEW_IMPORT) == 1
                and normalized.count(NEW_BLOCK) == 1):
            ast.parse(normalized)
            return source, "already_applied"
        raise RuntimeError("Partial or duplicate 36-5 patch marker")
    if normalized.count(OLD_IMPORT) != 1 or normalized.count(OLD_BLOCK) != 1:
        raise RuntimeError("Expected unmodified 36-4 import and diagnostic anchors")
    result = normalized.replace(OLD_IMPORT, NEW_IMPORT, 1).replace(OLD_BLOCK, NEW_BLOCK, 1)
    ast.parse(result)
    if "\r\n" in text:
        result = result.replace("\n", "\r\n")
    return result.encode("utf-8"), "ready"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Batch36-5 additive quality-evidence installer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if not TARGET.is_file():
        parser.error(f"Missing {TARGET}. Run from repository root.")
    service = Path("backend/app/services/style_alignment_quality_service.py")
    if not service.is_file():
        parser.error(f"Missing {service}. Extract ZIP to project root first.")
    try:
        ast.parse(service.read_text(encoding="utf-8"))
        updated, status = patch(TARGET.read_bytes())
    except (OSError, SyntaxError, UnicodeError, RuntimeError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    if args.check:
        print("36-5 quality-evidence check:", status)
    elif status == "ready":
        TARGET.write_bytes(updated)
        print("36-5 quality-evidence applied:", TARGET)
    else:
        print("36-5 quality-evidence already applied:", TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
